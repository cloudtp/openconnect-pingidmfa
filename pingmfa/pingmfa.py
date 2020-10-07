#!/usr/bin/env python3
import argparse
import getpass
import glob
import os
import sys
import shlex
import signal
import subprocess
import time
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

import elevate
import selenium.common.exceptions
import yaml
from pykeepass import PyKeePass
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys

pid_path = "/var/run/pingmfa"
default_config_path = "/etc/pingmfa.conf"
default_server = "https://global.remoteaccess.hp.com"
default_browser = "google-chrome"

class ConfigurationWindow(Gtk.Window):
    def __init__(self):
        Gtk.Window.__init__(self, title="PingID MFA Configuration Tool")

        self.mainBox = Gtk.Box(spacing=6)
        self.add(self.mainBox)

        self.serverBox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)

        self.ServerLabel = Gtk.Label(label="Server URL:")
        self.ServerTextBox = Gtk.Entry()
        self.ServerTextBox.set_placeholder_text("example.com")

        self.serverBox.pack_start(self.ServerLabel, True, True, 0)
        self.serverBox.pack_start(self.ServerTextBox, True, True, 0)

        self.mainBox.pack_start(self.serverBox, True, True, 0)

        self.passwordSwitcher = Gtk.StackSwitcher()
        

def parse_arguments():
    """
    Parse command line arguments
    :return:
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "-t", "--terminate", "--close", action="store_true", help="Close current connection")
    parser.add_argument("--config", default=default_config_path,
                        help="Alternative path to configuration file; default {}".format(default_config_path))
    parser.add_argument("--email", default=None, help="Plaintext email credential")
    parser.add_argument("--password", default=None, help="Plaintext password; not recommended")
    parser.add_argument("--store", default=None, help="Enable external password store; default: None")
    parser.add_argument("--show", action="store_true", help="Enable visible browser during login")
    parser.add_argument("--browser", default="Chrome", help="Path to browser executable; default: google-chrome")
    parser.add_argument("--server", help="SSO Server to Authenticate against; default: {}".format(default_server))
    parser.add_argument("--configure", action="store_true", help="Walk user through building configuration file")
    parser.add_argument("--echo", action="store_true")
    parser.add_argument("--attempts", default=10, help="Number of attempts to create connection with VPN server")
    return parser.parse_args()


def is_atty():
    """
    Check if shell is interactive
    :return:
    """
    return os.isatty(sys.stdout.fileno())


def is_root():
    """
    Check if user has root permissions
    :return:
    """
    return os.geteuid() == 0


def get_command_pid(command):
    for path in glob.glob('/proc/*/comm'):
        if open(path).read().rstrip() == command:
            return path.split('/')[2]


def terminate():
    """
    Lookup PID and terminate current openconnect found at PID
    :return:
    """
    with open(pid_path) as pid_file:
        PID = pid_file.read().rstrip()

    FPID = get_command_pid("openconnect")

    if FPID == PID:
        os.kill(int(PID), signal.SIGTERM)


def load_conf(config_path):
    """
    Load the configuration file
    :return:
    """
    try:
        with open(os.path.expandvars(os.path.expanduser(config_path))) as config_file:
            config = yaml.load(config_file, Loader=yaml.FullLoader)
    except FileNotFoundError:
        print("No configuration found. To create configuration try \"pingmfa --configure\"")
        config = {}
    return config


def configure():
    """
    Configure and post config to appropriate directory
    :return:
    """
    window = ConfigurationWindow()
    window.connect("destroy", Gtk.main_quit)
    window.show_all()
    Gtk.main()


def main():
    """
    Out main processing function
    :return:
    """
    if not is_root():
        if is_atty():
            elevate.elevate(graphical=False)
        else:
            elevate.elevate()

    args = parse_arguments()

    if args.terminate:
        terminate()
        exit()

    if args.configure:
        configure()
        exit()

    # load configuration
    config = load_conf(args.config)

    if "url" not in config:
        config["url"] = input("Enter SSO gateway: ")

    # look for credentials in the arguments
    if args.email is None:
        if "store" in config:

            if "email" in config["store"]:
                email = config["store"]["email"]

            if "password" in config["store"]:
                password = config["store"]["password"]

            elif "type" in config["store"]:
                if config["store"]["type"] == "keepassxc":
                    kp_password = getpass.getpass("Enter KeepassXC Password: ")
                    kp = PyKeePass(config["store"]["database"], password=kp_password)
                    entry = kp.find_entries_by_path(config["store"]["entry"])
                    email = entry.username
                    password = entry.password
    else:
        email = args.email

    options = Options()
    if not args.show:
        options.headless = True
        options.add_argument("--no-sandbox")

    browser = webdriver.Chrome(
        executable_path="/usr/local/bin/chromedriver",
        options=options
    )
    browser.get(config["url"])
    time.sleep(1)

    assert "HPE Log on" in browser.title
    input_username = browser.find_element_by_name("pf.username")
    input_username.clear()
    input_username.send_keys(email)

    input_password = browser.find_element_by_name("pf.pass")
    input_password.clear()
    input_password.send_keys(password)
    input_password.send_keys(Keys.RETURN)

    print("Waiting for PingID MFA Approval")
    while browser.title != "Pulse Connect Secure - Home":
        if "HP Global VPN - Confirmation Open Sessions" in browser.title:
            try:
                input_postfix_sid = browser.find_element_by_name("postfixSID")
                input_postfix_sid.click()
            except selenium.common.exceptions.NoSuchElementException:
                pass

            try:
                input_btn_continue = browser.find_element_by_name("btnContinue")
                input_btn_continue.click()
            except selenium.common.exceptions.NoSuchElementException:
                time.sleep(1)

    cookies = browser.get_cookies()
    for cookie in cookies:
        if cookie["name"] == "DSID":
            dsid = cookie["value"]

    browser.quit()

    if args.echo:
        print(
            "/usr/sbin/openconnect --pid-file=/var/run/pingmfa --background --protocol nc -C DSID={} https://global.remoteaccess.hp.com".format(
                dsid))
        exit()

    attempt_count = 0
    while attempt_count < args.attempts:
        command = "/usr/sbin/openconnect --pid-file=/var/run/pingmfa --background --protocol nc -C DSID={} https://global.remoteaccess.hp.com".format(
            dsid)
        cmd_args = shlex.split(command)
        result = subprocess.run(cmd_args)
        attempt_count += 1
        if result.returncode == 0:
            exit()
        time.sleep(1)


if __name__ == "__main__":
    main()

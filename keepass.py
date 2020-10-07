from pykeepass import PyKeePass

kp = PyKeePass("/home/utahcon/keepass/cloudtp.kdbx", password="Dragen02.@")

groups = {}

for group in kp.groups:
    if not group.is_root_group:
        groups[group.name] = {}
        print("Group: {} | Parent: {}".format(group.name, group.parentgroup))

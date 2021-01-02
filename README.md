# vmware_guest_pci
- This is an Ansible module that adds and remove pci devices from Vmware vms
## Examples
```
- hosts: localhost
  collections:
    - community.vmware
  tasks:
    - name: add pci
      community.vmware.vmware_guest_pci:
        hostname: "{{ vcenter_hostname }}"
        username: "{{ vcenter_username }}"
        password: "{{ vcenter_password }}"
        datacenter: "{{ datacenter_name }}"
        name: matan-test
        pci_id: '0000:0b:00.0'
        state: present

```

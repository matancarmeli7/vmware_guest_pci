#!/usr/bin/python

from __future__ import absolute_import, division, print_function

__metaclass__ = type

try:
    from pyVmomi import vim
except ImportError:
    pass

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.community.vmware.plugins.module_utils.vmware import (
    PyVmomi, vmware_argument_spec, wait_for_task)


class PyVmomiHelper(PyVmomi):
    def __init__(self, module):
        super(PyVmomiHelper, self).__init__(module)

    def _pci_absent(self, vm_obj):
        result = {}
        pci_id = self.params['pci_id']
        pci_VirtualDevice_obj = self._get_pci_VirtualDevice_object(vm_obj, pci_id)
        if pci_VirtualDevice_obj is None:
            changed = False
            failed = False
        else:
            changed, failed = self._remove_pci_device_from_vm(vm_obj, pci_VirtualDevice_obj, pci_id)
        result = {'changed': changed, 'failed': failed}
        return result

    def _remove_pci_device_from_vm(self, vm_obj, pci_VirtualDevice_obj, pci_id):
        changed = False
        failed = False
        vm_current_pci_devices = self._get_the_pci_devices_in_the_vm(vm_obj)
        if pci_id in vm_current_pci_devices:
            vdspec = vim.vm.device.VirtualDeviceSpec()
            vmConfigSpec = vim.vm.ConfigSpec()
            vdspec.operation = 'remove'
            vdspec.device = pci_VirtualDevice_obj
            vmConfigSpec.deviceChange.append(vdspec)
            try:
                task = vm_obj.ReconfigVM_Task(spec=vmConfigSpec)
                wait_for_task(task)
                changed = True
                return changed, failed
            except Exception as exc:
                failed = True
                self.module.fail_json(msg="Failed to delete Pci device"
                                          " '{}' from vm {}.".format(pci_id, vm_obj.name),
                                          detail=exc.msg)
        return changed, failed

    def _pci_present(self, vm_obj):
        result = {}
        pci_id = self.params['pci_id']
        pci_Passthrough_device_obj = self._get_pci_Passthrough_object(vm_obj, pci_id)
        if pci_Passthrough_device_obj is None:
            self.module.fail_json(msg="Pci device '{}'"
                                      " does not exist.".format(pci_id))
        changed, failed = self._add_pci_device_to_vm(vm_obj, pci_Passthrough_device_obj, pci_id)
        result = {'changed': changed, 'failed': failed}
        return result

    def _add_pci_device_to_vm(self, vm_obj, pci_Passthrough_device_obj, pci_id):
        changed = False
        failed = False
        vm_current_pci_devices = self._get_the_pci_devices_in_the_vm(vm_obj)
        if self.params['force'] or pci_id not in vm_current_pci_devices:
            deviceid = hex(pci_Passthrough_device_obj.pciDevice.deviceId % 2**16).lstrip('0x')
            systemid = pci_Passthrough_device_obj.systemId
            backing = vim.VirtualPCIPassthroughDeviceBackingInfo(deviceId=deviceid,
                                                                 id=pci_id,
                                                                 systemId=systemid,
                                                                 vendorId=pci_Passthrough_device_obj.pciDevice.vendorId,
                                                                 deviceName=pci_Passthrough_device_obj.pciDevice.deviceName)
            hba_object = vim.VirtualPCIPassthrough(key=-100, backing=backing)
            new_device_config = vim.VirtualDeviceConfigSpec(device=hba_object)
            new_device_config.operation = "add"
            vmConfigSpec = vim.vm.ConfigSpec()
            vmConfigSpec.deviceChange = [new_device_config]
            vmConfigSpec.memoryReservationLockedToMax = True

            try:
                task = vm_obj.ReconfigVM_Task(spec=vmConfigSpec)
                wait_for_task(task)
                changed = True
            except Exception as exc:
                failed = True
                self.module.fail_json(msg="Failed to add Pci device"
                                          " '{}' to vm {}.".format(pci_id, vm_obj.name),
                                          detail=exc.msg)
        else:
            return changed, failed
        return changed, failed

    def _get_the_pci_devices_in_the_vm(self, vm_obj):
        vm_current_pci_devices = []
        for pci_VirtualDevice_obj in vm_obj.config.hardware.device:
            if hasattr(pci_VirtualDevice_obj.backing, 'id'):
                vm_current_pci_devices.append(pci_VirtualDevice_obj.backing.id)
        return vm_current_pci_devices

    def _get_pci_VirtualDevice_object(self, vm_obj, pci_id):
        for pci_VirtualDevice_obj in vm_obj.config.hardware.device:
            if hasattr(pci_VirtualDevice_obj.backing, 'id'):
                if pci_VirtualDevice_obj.backing.id == pci_id:
                    return pci_VirtualDevice_obj
        return None

    def _get_pci_Passthrough_object(self, vm_obj, pci_id):
        pci_passthroughs = vm_obj.environmentBrowser.QueryConfigTarget(
            host=None).pciPassthrough
        for pci_Passthrough_device_obj in pci_passthroughs:
            if pci_Passthrough_device_obj.pciDevice.id == pci_id:
                return pci_Passthrough_device_obj
        return None


def main():
    argument_spec = vmware_argument_spec()
    argument_spec.update(
        name=dict(type='str'),
        uuid=dict(type='str'),
        use_instance_uuid=dict(type='bool', default=False),
        moid=dict(type='str'),
        folder=dict(type='str'),
        datacenter=dict(type='str', default='ha-datacenter'),
        esxi_hostname=dict(type='str'),
        cluster=dict(type='str'),
        pci_id=dict(type='str'),
        force=dict(type='bool', default=False),
        state=dict(type='str', default='present', choices=['absent', 'present'])
    )

    module = AnsibleModule(
        argument_spec=argument_spec,
        mutually_exclusive=[
            ['cluster', 'esxi_hostname']
        ],
        required_one_of=[
            ['name', 'uuid', 'moid']
        ],
        # supports_check_mode=True
    )

    pyv = PyVmomiHelper(module)
    vm = pyv.get_vm()

    if not vm:
        vm_id = (module.params.get('uuid') or module.params.get('name') or module.params.get('moid'))
        module.fail_json(msg="Unable to manage pci devices for non-existing VM {}".format(vm_id))

    if module.params['state'] == 'present':
        result = pyv._pci_present(vm)
    elif module.params['state'] == 'absent':
        result = pyv._pci_absent(vm)

    if 'failed' not in result:
        result['failed'] = False

    if result['failed']:
        module.fail_json(**result)
    else:
        module.exit_json(**result)


if __name__ == '__main__':
    main()

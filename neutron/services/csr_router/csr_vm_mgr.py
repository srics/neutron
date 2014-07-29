# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright (c) 2013 OpenStack Foundation.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
#
# @author: Sridhar Ramaswamy, Cisco Systems, Inc.


if __name__ == '__main__':
    import logging
else:
    from neutron.openstack.common import log as logging

from novaclient      import exceptions as nova_exceptions
from novaclient.v1_1 import client as nova_client


LOG = logging.getLogger(__name__)

class CSRVMManager():

    def __init__(self):
        """Initialize CSR Virtual Machine Manager
        """
        creds = self._get_nova_creds()
        try:
            self._nova_client = nova_client.Client(**creds)
        except:
            LOG.error('CSR:nova client connection failed')
            return
        LOG.debug('CSR-MSG: Connected to nova')


    def _get_nova_creds(self):
        d = {}
        d['username'] = 'admin'
        d['api_key'] = 'nova'
        d['auth_url'] = 'http://172.19.162.33:5000/v2.0'
        d['project_id'] = 'csr'
        return d

    def _get_vm_name(self, router_name):
        return "_CSR_" + router_name

    def _get_csr_flavor(self):
        try:
            flavor = self._nova_client.flavors.find(name="csr-medium-public")
        except nova_exceptions.NotFound:
            LOG.error('CSR-MSG: nova flavor not found')
            # TODO: raise a new exception
        return flavor

    def _get_csr_image(self):
        try:
            image = self._nova_client.images.find(name="csr-3.13-mcp")
        except nova_exceptions.NotFound:
            LOG.error('CSR-MSG: nova csr image find failed')
            # TODO: raise a new exception
            return None
        return image

    def launch_csr(self, router_name, port_id=None):
        """
        Create CSR VM instance using nova client API

        :param router_name:
        :return Server object of new VM:
        """
        LOG.debug('CSR-MSG: inside launch_csr() for router %s port-id %s', router_name, port_id)

        flavor = self._get_csr_flavor()
        image = self._get_csr_image()

        vm_name = self._get_vm_name(router_name)
        LOG.debug('CSR-MSG: Launch CSR instance  %s', vm_name)
        server = self._nova_client.servers.create(name=vm_name,
                                        image=image.id,
                                        flavor=flavor.id,
                                        # nics=[{"port-id": port_id}]
                                            )

        LOG.debug('CSR-MSG: Server status %s', server.status)
        return

    def remove_csr(self, router_name):
        LOG.debug('CSR-MSG: inside remove_csr()')
        vm_name = self._get_vm_name(router_name)
        server = self.findserver(vm_name)
        self._nova_client.servers.delete(server)
        LOG.debug('CSR-MSG: leaving remove_csr()')
        return

    def findserver(self, vm_name):
        my_search_opts = {}
        my_search_opts['name'] = vm_name
        server_list = self._nova_client.servers.list(detailed=False,limit=1,search_opts=my_search_opts)
        LOG.debug('CSR-MSG: findserver() %s', server_list[0])
        return server_list[0]

    def create_mgmt_vnic_port(self, context, router_name, tenant_id):
        port_name = "_CSR_mgmt_port_" + router_name
        # get "public" network id
        net = self._core_plugin.get_networks(context,filters={'name':['public']}, fields=['id','name'])
        network_id = net[0]['id']
        LOG.debug(' CSR-MSG: create_vnic_port(): network id %s', net[0]['id'])
        return self._create_vnic_port(context, port_name, tenant_id, network_id)

    def create_ingress_vnic_port(self, context, router_name, tenant_id):
        port_name = "_CSR_ingress_port_" + router_name
        return self._create_vnic_port(context, port_name, tenant_id)

    def create_egress_vnic_port(self, context, router_name, tenant_id):
        port_name = "_CSR_egress_port_" + router_name
        # get  "public" network
        net = self._core_plugin.get_networks(context,filters={'name':['public']}, fields=['id','name'])
        network_id = net[0]['id']
        LOG.debug(' CSR-MSG: create_vnic_port(): network id %s', net[0]['id'])
        return self._create_vnic_port(context, port_name, tenant_id, network_id)

    def _create_vnic_port(self, context, port_name, tenant_id):
        LOG.debug(' CSR-MSG: create_vnic_port(): inside rname %s', rname)

        # 1. Get admin tenant-id
        # 2. Create port on "public" subnet
        # Create port for mgmt interface

        # TODO(Sridhar.R): revisit security group setting

        # get id of "public" network
        net = self._core_plugin.get_networks(context,filters={'name':['public']}, fields=['id','name'])
        network_id = net[0]['id']
        LOG.debug(' CSR-MSG: create_vnic_port(): network id %s', net[0]['id'])

        # get id of "public-subnet" subnet
        #subnet = self._core_plugin.get_subnets(context,filters={'name':['public-subnet']},fields=['id','name'])
        subnet = self._core_plugin.get_subnets(context,filters=None,fields=['id','name'])
        LOG.debug(' CSR-MSG: create_vnic_port(): subnet id %s', subnet)
        subnet_id = '0c2ae3bd-26d7-44fa-bd6e-34f4521f7a5b'
        #subnet_id = subnet[0]['id']

        # Create port
        port_spec = {'port': {
                        'tenant_id': tenant_id,  # current tenant-id
                        'admin_state_up': True,
                        'name': 'csr-nic-1' + port_name,
                        'network_id': network_id,
                        'mac_address': attributes.ATTR_NOT_SPECIFIED,
                        'fixed_ips': [{'subnet_id':subnet_id, 'ip_address' : '172.24.4.100'}],
                        'security_groups': [],
                        'device_id': "",
                        'device_owner': ""
                        }
                    }

        port = self._core_plugin.create_port(context, port_spec)
        LOG.debug(' CSR-MSG: create_vnic_port(): port object %s', port)
        LOG.debug(' CSR-MSG: create_vnic_port(): created port status %s', port['status'])
        LOG.debug(' CSR-MSG: create_vnic_port(): created port id %s', port['id'])
        return port

if __name__ == '__main__':
    import time

    # Prepare logging for standlone invocation
    LOG.setLevel(logging.DEBUG)
    fh = logging.FileHandler('mylog.log')
    LOG.addHandler(fh)
    fh.setLevel(logging.DEBUG)

    LOG.debug('Inside main()')
    csr_mgr = CSRVMManager()
    csr_mgr.launch_csr("test12345")

    LOG.debug('sleeping ')
    time.sleep(10)

    csr_mgr.remove_csr("test1234")

    LOG.debug('Leaving main()')

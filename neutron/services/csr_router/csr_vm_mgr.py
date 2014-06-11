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
from novaclient.v1_1 import client
from novaclient.v1_1 import servers


LOG = logging.getLogger(__name__)

class CSRVMManager():

    def __init__(self):
        """Initialize CSR Virtual Machine Manager
        """

    def get_nova_creds(self):
        d = {}
        d['username'] = 'csr'
        d['api_key'] = 'nova'
        d['auth_url'] = 'http://172.19.162.33:5000/v2.0'
        d['project_id'] = 'csr'
        return d

    def _get_vm_name(self, router_name):
        return "_CSR_" + router_name

    def launch_csr(self, router_name):
        LOG.debug('CSR-MSG: inside launch_csr()')
        try:
            creds = self.get_nova_creds()
            nclient = client.Client(**creds)
        except:
            LOG.error('CSR:nova client connection failed')
            return
        LOG.debug('CSR-MSG: Connected to nova')

        try:
            flavor = nclient.flavors.find(name="csr-medium")
        except:
            LOG.error('CSR-MSG: nova flavor find failed')
            return
        LOG.debug('CSR-MSG: Found csr flavor')

        try:
            image = nclient.images.find(name="csr-3.13-mcp")
        except:
            LOG.error('CSR-MSG: nova csr image find failed')
            return
        LOG.debug('CSR-MSG: Found csr image')

        vm_name = self._get_vm_name(router_name)
        LOG.debug('CSR-MSG: Launch CSR instance name %s', vm_name)
        server = nclient.servers.create(name=vm_name,
                                        image=image.id,
                                        flavor=flavor.id)

        LOG.debug('CSR-MSG: Server status %s', server.status)
        return

    def remove_csr(self, router_name):
        LOG.debug('CSR-MSG: inside remove_csr()')

        try:
            creds = self.get_nova_creds()
            nclient = client.Client(**creds)
        except:
            LOG.error('CSR:nova client connection failed')
            return
        LOG.debug('CSR-MSG: Connected to nova')

        vm_name = self._get_vm_name(router_name)
        server = self.findserver(router_name)
        nclient.servers.delete(server)
        LOG.debug('CSR-MSG: leaving remove_csr()')
        return

    def findserver(self, router_name):
        try:
            creds = self.get_nova_creds()
            nclient = client.Client(**creds)
        except:
            LOG.error('CSR:nova client connection failed')
            return
        LOG.debug('CSR-MSG: Connected to nova')
        my_search_opts = {}
        my_search_opts['name'] = router_name
        server_list = nclient.servers.list(detailed=False,limit=1,search_opts=my_search_opts)
        print server_list[0]
        return server_list[0]

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

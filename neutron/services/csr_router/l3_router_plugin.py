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
# @author: Bob Melander, Cisco Systems, Inc.
# @author: Sridhar Ramaswamy, Cisco Systems, Inc.

import os
from oslo.config import cfg

from neutron.api.rpc.agentnotifiers import l3_rpc_agent_api
from neutron import context as neutron_context
from neutron import manager
from neutron.api.v2 import attributes
from neutron.common import constants as q_const
from neutron.common import rpc as q_rpc
from neutron.common import topics
from neutron.db import api as qdbapi
from neutron.db import db_base_plugin_v2
from neutron.db import extraroute_db
from neutron.db import l3_agentschedulers_db
from neutron.db import l3_gwmode_db
from neutron.db import l3_rpc_base
from neutron.db import model_base
from neutron.openstack.common import log as logging
from neutron.openstack.common import importutils
from neutron.openstack.common import rpc
from neutron.plugins.common import constants

from csr_vm_mgr import CSRVMManager

LOG = logging.getLogger(__name__)

class L3RouterPluginRpcCallbacks(l3_rpc_base.L3RpcCallbackMixin):

    RPC_API_VERSION = '1.1'

    def create_rpc_dispatcher(self):
        """Get the rpc dispatcher for this manager.

        If a manager would like to set an rpc API version, or support more than
        one class as the target of rpc messages, override this method.
        """
        return q_rpc.PluginRpcDispatcher([self])


class L3RouterPlugin(db_base_plugin_v2.CommonDbMixin,
                     extraroute_db.ExtraRoute_db_mixin,
                     l3_gwmode_db.L3_NAT_db_mixin,
                     l3_agentschedulers_db.L3AgentSchedulerDbMixin):

    """Implementation of the Neutron L3 Router Service Plugin.

    This class implements a L3 service plugin that provides
    router and floatingip resources and manages associated
    request/response.
    All DB related work is implemented in classes
    l3_db.L3_NAT_db_mixin and extraroute_db.ExtraRoute_db_mixin.
    """
    supported_extension_aliases = ["router", "ext-gw-mode",
                                   "extraroute", "l3_agent_scheduler"]

    def __init__(self):
        qdbapi.register_models(base=model_base.BASEV2)
        self.setup_rpc()
        self.router_scheduler = importutils.import_object(
            cfg.CONF.router_scheduler_driver)

    def setup_rpc(self):
        # RPC support
        self.topic = topics.L3PLUGIN
        self.conn = rpc.create_connection(new=True)
        self.agent_notifiers.update(
            {q_const.AGENT_TYPE_L3: l3_rpc_agent_api.L3AgentNotify})
        self.callbacks = L3RouterPluginRpcCallbacks()
        self.dispatcher = self.callbacks.create_rpc_dispatcher()
        self.conn.create_consumer(self.topic, self.dispatcher,
                                  fanout=False)
        self.conn.consume_in_thread()

    def get_plugin_type(self):
        return constants.L3_ROUTER_NAT

    def get_plugin_description(self):
        """returns string description of the plugin."""
        return ("L3 Router Service Plugin for basic L3 forwarding"
                " between (L2) Neutron networks and access to external"
                " networks via a NAT gateway.")

    def create_floatingip(self, context, floatingip):
        """Create floating IP.

        :param context: Neutron request context
        :param floatingip: data fo the floating IP being created
        :returns: A floating IP object on success

        AS the l3 router plugin aysnchrounously creates floating IPs
        leveraging tehe l3 agent, the initial status fro the floating
        IP object will be DOWN.
        """
        LOG.debug(' CSR-MSG: csr_router:l3_router_plugin: inside create_floatingip()')
        return super(L3RouterPlugin, self).create_floatingip(
            context, floatingip,
            initial_status=q_const.FLOATINGIP_STATUS_DOWN)

    def create_router(self, context, router):
        """ CSR Create Router

        :param context: Neutron request context
        :param router:
        :returns:
        """
        r = router['router']
        router_name = r['name']
        tenant_id = r['tenant_id']

        LOG.debug(' CSR-MSG: csr_router:l3_router_plugin: inside create_router() name %s tenant-id %s',
                  router_name, tenant_id)
        # TODO: connect with admin privilege

        # Create mgmt vnic
        port = self.create_vnic_port(context, router_name, tenant_id)
        self.csr_vm_mgr.launch_csr(router_name, port['id'])
        return super(l3_gwmode_db.L3_NAT_db_mixin, self).create_router(context, router)

    def delete_router(self, context, id):
        """
        :param context:
        :param id:
        :return:
        """
        router = self._get_router(context, id)
        router_name = router.name

        LOG.debug(' CSR-MSG: csr_router:l3_router_plugin: inside delete_router() name %s', router_name)
        self.csr_vm_mgr.remove_csr(router_name)

        return super(l3_gwmode_db.L3_NAT_db_mixin, self).delete_router(context, id)

    def create_mgmt_vnic_port(self, context, router_name, tenant_id):
        port_name = "_CSR_mgmt_port_" + router_name
        # get "public" network id
        net = self._core_plugin.get_networks(context,filters={'name':['public']}, fields=['id','name'])
        network_id = net[0]['id']
        LOG.debug(' CSR-MSG: create_vnic_port(): network id %s', net[0]['id'])
        return self._create_vnic_port(context, port_name, tenant_id, network_id)

    def create_private_vnic_port(self, context, router_name, tenant_id):
        port_name = "_CSR_ingress_port_" + router_name
        return self._create_vnic_port(context, port_name, tenant_id)

    def create_public_vnic_port(self, context, router_name, tenant_id):
        port_name = "_CSR_egress_port_" + router_name
        # get  "public" network
        net = self._core_plugin.get_networks(context,filters={'name':['public']}, fields=['id','name'])
        network_id = net[0]['id']
        LOG.debug(' CSR-MSG: create_vnic_port(): network id %s', net[0]['id'])
        return self._create_vnic_port(context, port_name, tenant_id, network_id)

    def _create_vnic_port(self, context, port_name, tenant_id, network_id=None):
        LOG.debug(' CSR-MSG: create_vnic_port(): inside rname %s', rname)

        # 1. Get admin tenant-id
        # 2. Create port on "public" subnet
        # Create port for mgmt interface

        # TODO(Sridhar.R): revisit security group setting

        # get id of "public" network
        # net = self._core_plugin.get_networks(context,filters={'name':['public']}, fields=['id','name'])
        # network_id = net[0]['id']
        LOG.debug(' CSR-MSG: create_vnic_port(): network id %s', network_id)

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

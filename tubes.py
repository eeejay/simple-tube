from dbus_pprint import dbus_pprint
import getpass, sys
import dbus, gobject, telepathy
import dbus.glib # sets up a main loop (!!!); somewhat deprecated
from functools import partial

from accountmgr import AccountManager
from account import Account

from telepathy.constants import (
    CONNECTION_HANDLE_TYPE_CONTACT, HANDLE_TYPE_LIST,
    CHANNEL_TEXT_MESSAGE_TYPE_NORMAL,
    TUBE_TYPE_DBUS, TUBE_STATE_LOCAL_PENDING, TUBE_STATE_OPEN,
    CONNECTION_STATUS_CONNECTED, CONNECTION_STATUS_DISCONNECTED,
    SOCKET_ACCESS_CONTROL_LOCALHOST)
from telepathy.interfaces import (
    CHANNEL, CHANNEL_INTERFACE_GROUP, CHANNEL_TYPE_CONTACT_LIST,
    CHANNEL_TYPE_DBUS_TUBE,
    CONNECTION, CONNECTION_INTERFACE_REQUESTS,
    CONNECTION_INTERFACE_CONTACTS,
    CONNECTION_INTERFACE_ALIASING,
    CONNECTION_INTERFACE_SIMPLE_PRESENCE,
    CONNECTION_INTERFACE_CONTACT_CAPABILITIES,
    CONNECTION_INTERFACE_CAPABILITIES,
    CHANNEL_INTERFACE_TUBE,
    CLIENT, CLIENT_HANDLER,
    ACCOUNT_MANAGER, ACCOUNT)

DBUS_PROPERTIES = 'org.freedesktop.DBus.Properties'

SERVICE = 'com.example.OurEditor' # domain name, backwards
PATH = '/' + SERVICE.replace('.', '/')
TUBETYPE = SERVICE.replace('.', '_')

# Note on the TUBETYPE: in principle, it should be equal to the SERVICE;
# however, in some places, a single word is required...

class Example(dbus.service.Object,
              #telepathy._generated.Client_Handler.ClientHandler,
              telepathy.server.DBusProperties):
    def __init__(self):
        self.buddies = {}
        self._interfaces = set([CLIENT, CLIENT_HANDLER, DBUS_PROPERTIES])
        self.service_name = CLIENT+'.'+TUBETYPE
        object_path = '/'+self.service_name.replace('.', '/')


        dbus.service.Object.__init__(self, bus, object_path)
        telepathy.server.DBusProperties.__init__(self)
        self._implement_property_get(CLIENT, {
            'Interfaces': lambda: [CLIENT, CLIENT_HANDLER, DBUS_PROPERTIES],
          })
        self._implement_property_get(CLIENT_HANDLER, {
            'HandlerChannelFilter': lambda: dbus.Array([
                dbus.Dictionary({
                    CHANNEL + '.ChannelType'     : CHANNEL_TYPE_DBUS_TUBE,
                    CHANNEL + '.TargetHandleType': CONNECTION_HANDLE_TYPE_CONTACT,
                    CHANNEL_TYPE_DBUS_TUBE + '.ServiceName'    : SERVICE,
                }, signature='sv')
            ], signature='a{sv}'),
            #'Capabilities': lambda: dbus.Array([SERVICE], signature='as'),
          })
        #bus.request_name(self.service_name)
        self.name_ownership = dbus.service.BusName(self.service_name, bus=bus)

    def new_conn(self, conn):
        conn.call_when_ready(self.ready_cb)

    def ready_cb(self, conn):
        """ Called when the connection is ready... """

        # get list of buddies:
        self.get_roster(conn)

        # buddies will be contacted as their details come in...

    def get_roster(self, conn):
        conn[CONNECTION_INTERFACE_CONTACT_CAPABILITIES].connect_to_signal(
                  'ContactCapabilitiesChanged',
                  partial(self.contact_capabilities_changed, conn))
        for group in ('subscribe', 'publish', 'stored', 'known'):
            conn[CONNECTION_INTERFACE_REQUESTS].EnsureChannel({
                CHANNEL + '.ChannelType'     : CHANNEL_TYPE_CONTACT_LIST,
                CHANNEL + '.TargetHandleType': HANDLE_TYPE_LIST,
                CHANNEL + '.TargetID'        : group,
                },
                reply_handler = partial(self.member_channel_cb, conn),
                error_handler = partial(self.roster_error_cb, group))

    def roster_error_cb(self, group, *args):
        if group=='known':
            print 'Info: could not retrieve the obsolete "known contacts" list'
            print 'The error was:', args
        else:
            print 'Warning: could not retrieve the "%s contacts" list'%group
            print 'The error was:', args

    def member_channel_cb(self, conn, yours, path, properties):
        channel = telepathy.client.Channel(conn.service_name, path)
        channel[CHANNEL_INTERFACE_GROUP].connect_to_signal(
                  'MembersChanged', partial(self.members_changed_cb, conn))

        handles = channel[DBUS_PROPERTIES].Get(CHANNEL_INTERFACE_GROUP,
                                                                 'Members')

        handles = set(handles)
        print
        if conn.object_path in self.buddies:
            handles -= set(self.buddies[conn.object_path].keys())
        else:
            self.buddies[conn.object_path] = {}
        if handles:
            self.got_new_buddies(conn, handles)

    def got_new_buddies(self, conn, handles):
        attribs = conn[CONNECTION_INTERFACE_CONTACTS].GetContactAttributes(
                handles, [
                    CONNECTION,
                    CONNECTION_INTERFACE_ALIASING,
                    CONNECTION_INTERFACE_CONTACT_CAPABILITIES,
                ],
                False)
        self.buddies[conn.object_path].update(attribs)
        self.select_buddy(conn, handles)

    def contact_capabilities_changed(self, conn, changed_caps):
        # notes:
        #   1. We're only handling here the situation where contacts go
        #   online; going offline is also signalled here...
        #   2. We should check whether changed_caps contains the relevant
        #   capabilities, to save on re-retrieving irrelevant data.
        self.got_new_buddies(conn, changed_caps.keys())

    def members_changed_cb(self, conn, message, added, removed, local_pending,
            remote_pending, actor, reason):

        # Note: new buddies are signalled here, but not buddies that were
        # offline and have now come online (or vice versa).

        if added:
            self.got_new_buddies(conn, added)
        if removed:
            for handle in removed:
                member = self.conn[CONNECTION].InspectHandles(
                    CONNECTION_HANDLE_TYPE_CONTACT, [handle])[0]
                print 'buddy went away: %s' % member

    def select_buddy(self, conn, new_buddies):
        alias_key = CONNECTION_INTERFACE_ALIASING + '/alias'
        for buddy_h in new_buddies:
            buddy = self.buddies[conn.object_path][buddy_h][alias_key]
            if self.check_buddy_caps(conn, buddy_h):
                print "Got %s, contacting!"%buddy
                self.contact(conn, buddy_h)
            else:
                print "Contact %s can't handle %s, skipping."%(buddy, SERVICE)

    def check_buddy_caps(self, conn, buddy_h):
        alias_key = CONNECTION_INTERFACE_ALIASING + '/alias'
        caps = CONNECTION_INTERFACE_CONTACT_CAPABILITIES + '/caps'
        if caps not in self.buddies[conn.object_path][buddy_h]:
            print "No capabilities obtained for %s."%(self.buddies[conn.object_path][buddy_h][alias_key])
            return False
        for props, additional in self.buddies[conn.object_path][buddy_h][caps]:
            if props.get(CHANNEL_TYPE_DBUS_TUBE + '.ServiceName', '')==SERVICE:
                return True
        return False

    def contact(self, conn, buddy_h):
        conn[CONNECTION_INTERFACE_REQUESTS].EnsureChannel({
            CHANNEL + '.ChannelType'     : CHANNEL_TYPE_DBUS_TUBE,
            CHANNEL + '.TargetHandleType': CONNECTION_HANDLE_TYPE_CONTACT,
            CHANNEL + '.TargetHandle'    : buddy_h,
            CHANNEL_TYPE_DBUS_TUBE + '.ServiceName'    : SERVICE,
            },
            reply_handler = partial(self.tube_channel_cb, conn),
            error_handler = self.error_cb)

    def tube_channel_cb(self, conn, yours, path, properties):
        channel = telepathy.client.Channel(conn.service_name, path)
        addr = channel[CHANNEL_TYPE_DBUS_TUBE].Offer({}, SOCKET_ACCESS_CONTROL_LOCALHOST)
        channel[CHANNEL_INTERFACE_TUBE].connect_to_signal('TubeChannelStateChanged',
                    partial(self.tube_state_cb, conn, addr))

    def tube_state_cb(self, conn, addr, state):
        if state == TUBE_STATE_OPEN:
            print 'connected'
            tube = dbus.connection.Connection(addr)
            tube.add_signal_receiver(self.signal_cb)
            me = EgObject(tube, conn)
            other = tube.get_object(object_path=PATH)

            # now that the tube is open, can start using it!
            self.use_connection(me, other)

    def use_connection(self, me, other):
        me.Hello('hello from %s'%getpass.getuser())
        other.Method("xyzzy %s"%getpass.getuser(),
                  reply_handler=self.reply_cb, error_handler=self.error_cb)

    def signal_cb(self, *args, **kwargs):
        print 'Signal:', args, kwargs

    def reply_cb(self, *args):
        print 'Reply:', args

    def error_cb(self, *args):
        print 'Error:', args

    @dbus.service.method(dbus_interface=CLIENT_HANDLER,
                           in_signature='ooa(oa{sv})aota{sv}', out_signature='')
    def HandleChannels(self, acct, conn_path, channels, reqs_satisfied,
                                           user_action_time, handler_info):
        print 'incoming channel'
        conn_name = conn_path.replace('/', '.')[1:]
        conn = telepathy.client.Connection(conn_name, conn_path)
        for path, props in channels:
            assert props[CHANNEL + '.ChannelType'] == CHANNEL_TYPE_DBUS_TUBE
            assert props[CHANNEL_TYPE_DBUS_TUBE + '.ServiceName'] == SERVICE
            assert not props[CHANNEL + '.Requested']
            channel = telepathy.client.Channel(conn_name, path)
            addr = channel[CHANNEL_TYPE_DBUS_TUBE].Accept(SOCKET_ACCESS_CONTROL_LOCALHOST)
            channel[CHANNEL_INTERFACE_TUBE].connect_to_signal(
              'TubeChannelStateChanged', partial(self.tube_state_cb, conn, addr))
            if len(handler_info):
                print 'handler info:',
                dbus_pprint(handler_info)


class EgObject(dbus.service.Object):
    def __init__(self, tube, conn):
        super(EgObject, self).__init__(tube, PATH)
        self.tube = tube

    @dbus.service.signal(dbus_interface=SERVICE, signature='s')
    def Hello(self, msg):
        pass

    @dbus.service.method(dbus_interface=SERVICE, in_signature='s',
                                                         out_signature='b')
    def Method(self, text):
        print "Method called: %s" % text
        return True


def connections_change_cb(e, *args, **kwargs):
    path = kwargs['path']
    if not path.startswith('/org/freedesktop/Telepathy/Connection/'):
        return

    status, reason = args
    service_name = path.replace('/', '.')[1:]

    if status == CONNECTION_STATUS_CONNECTED:
        print "new connection:", service_name, 'reason:', reason
        e.new_conn(telepathy.client.Connection(service_name, path))
    elif status == CONNECTION_STATUS_DISCONNECTED:
        print "connection gone:", service_name, 'reason:', reason

if __name__ == '__main__':

    # get the list of connections
    bus = dbus.SessionBus()

    e = Example()

    # add a handler that watches for changes
    bus.add_signal_receiver(partial(connections_change_cb, e),
        dbus_interface=CONNECTION, signal_name='StatusChanged',
        path_keyword='path')

    # work through the list of connections that are on-line
    am = AccountManager()
    for acct_path in am[DBUS_PROPERTIES].Get(ACCOUNT_MANAGER, 'ValidAccounts'):
        acct = Account(acct_path)
        conn_path = acct[DBUS_PROPERTIES].Get(ACCOUNT, 'Connection')
        if conn_path == '/':
            continue
        conn_name = conn_path.replace('/', '.')[1:]
        conn = telepathy.client.Connection(conn_name, conn_path)
        e.new_conn(conn)
        # note: the next step takes place in Example.ready_cb()

    try:
        gobject.MainLoop().run()
    except KeyboardInterrupt:
        print 'interrupted'

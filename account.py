from telepathy.client.interfacefactory import InterfaceFactory
from telepathy.interfaces import ACCOUNT, ACCOUNT_MANAGER
import dbus

DBUS_PROPERTIES = 'org.freedesktop.DBus.Properties'

class Account(InterfaceFactory):

    def __init__(self, object_path, bus=None):
        if not bus:
            bus = dbus.Bus()
        service_name = 'org.freedesktop.Telepathy.AccountManager'
        #service_name = object_path.replace('/', '.')[1:]

        object = bus.get_object(service_name, object_path)
        InterfaceFactory.__init__(self, object, ACCOUNT)

        # FIXME: make this async
        self.get_valid_interfaces().update(self[DBUS_PROPERTIES].Get(ACCOUNT, 'Interfaces'))

if __name__ == '__main__':
    from accountmgr import AccountManager
    from telepathy.client import Connection
    import gobject
    import dbus.glib # sets up a main loop (!!!); somewhat deprecated
    am = AccountManager()
    def show_conn(conn):
        print repr(conn)
    for acct_path in am[DBUS_PROPERTIES].Get(ACCOUNT_MANAGER, 'ValidAccounts'):
        acct = Account(acct_path)
        conn = acct[DBUS_PROPERTIES].Get(ACCOUNT, 'Connection')
        print conn
        conn = Connection(conn.replace('/', '.')[1:], conn)
        conn.call_when_ready(show_conn)
    gobject.MainLoop().run()

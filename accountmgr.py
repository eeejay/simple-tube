from telepathy.client.interfacefactory import InterfaceFactory
from telepathy.interfaces import ACCOUNT_MANAGER
import dbus

DBUS_PROPERTIES = 'org.freedesktop.DBus.Properties'

class AccountManager(InterfaceFactory):
    service_name = 'org.freedesktop.Telepathy.AccountManager'
    object_path = '/org/freedesktop/Telepathy/AccountManager'

    # Some versions of Mission Control are only activatable under this
    # name, not under the generic AccountManager name
    MC5_name = 'org.freedesktop.Telepathy.MissionControl5'
    MC5_path = '/org/freedesktop/Telepathy/MissionControl5'


    def __init__(self, bus=None):
        if not bus:
            bus = dbus.Bus()

        try:
            object = bus.get_object(self.service_name, self.object_path)
        except:
            raise
            # try activating MissionControl5 (ugly work-around)
            mc5 = bus.get_object(self.MC5_name, self.MC5_path)
            import time
            time.sleep(1)
            object = bus.get_object(self.service_name, self.object_path)
        InterfaceFactory.__init__(self, object, ACCOUNT_MANAGER)

        # FIXME: make this async
        self.get_valid_interfaces().update(self[DBUS_PROPERTIES].Get(ACCOUNT_MANAGER, 'Interfaces'))

if __name__ == '__main__':
    am = AccountManager()
    print am[DBUS_PROPERTIES].Get(ACCOUNT_MANAGER, 'ValidAccounts')

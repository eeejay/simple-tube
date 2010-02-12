from pprint import pprint
import dbus

def db2p(db):
    if type(db)==dbus.Struct:
        return tuple(db2p(i) for i in db)
    if type(db)==dbus.Array:
        return [db2p(i) for i in db]
    if type(db)==dbus.Dictionary:
        return dict((db2p(key), db2p(value)) for key, value in db.items())
    if type(db)==dbus.String:
        return db+''
    if type(db)==dbus.UInt32:
        return db+0
    if type(db)==dbus.Boolean:
        return db==True
    return ('type: %s'%type(db), db)

def dbus_pprint(data):
    pprint(db2p(data))

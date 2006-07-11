#! /usr/bin/env python
'''Imports statistics.xml and clients.xml files in to database backend for new statistics engine'''
__revision__ = '$Revision$'

import os, sys
try:    # Add this project to sys.path so that it's importable
    import settings # Assumed to be in the same directory.
except ImportError:
    sys.stderr.write("Failed to locate settings.py")
    sys.exit(1)

project_directory = os.path.dirname(settings.__file__)
project_name = os.path.basename(project_directory)
sys.path.append(os.path.join(project_directory, '..'))
project_module = __import__(project_name, '', '', [''])
sys.path.pop()
# Set DJANGO_SETTINGS_MODULE appropriately.
os.environ['DJANGO_SETTINGS_MODULE'] = '%s.settings' % project_name

from brpt.reports.models import Client, Interaction, Bad, Modified, Extra, Performance, Reason
from lxml.etree import XML, XMLSyntaxError
from sys import argv
from getopt import getopt, GetoptError
from datetime import datetime
from time import strptime, sleep

if __name__ == '__main__':

    try:
        opts, args = getopt(argv[1:], "hc:s:", ["help", "clients=", "stats="])
    except GetoptError, mesg:
        # print help information and exit:
        print "%s\nUsage:\nStatReports.py [-h] -c <clients-file> -s <statistics-file>" % (mesg) 
        raise SystemExit, 2
    for o, a in opts:
        if o in ("-h", "--help"):
            print "Usage:\nStatReports.py [-h] -c <clients-file> -s <statistics-file>"
            raise SystemExit
        if o in ("-c", "--clients"):
            clientspath = a
        if o in ("-s", "--stats"):
            statpath = a

    '''Reads Data & Config files'''
    try:
        statsdata = XML(open(statpath).read())
    except (IOError, XMLSyntaxError):
        print("StatReports: Failed to parse %s"%(statpath))
        raise SystemExit, 1
    try:
        clientsdata = XML(open(clientspath).read())
    except (IOError, XMLSyntaxError):
        print("StatReports: Failed to parse %s"%(clientspath))
        raise SystemExit, 1

    from django.db import connection, backend
    cursor = connection.cursor()

    clients = {}
    cursor.execute("SELECT name, id from reports_client;")
    [clients.__setitem__(a,b) for a,b in cursor.fetchall()]
    
    for node in statsdata.findall('Node'):
        name = node.get('name')
        if not clients.has_key(name):
            cursor.execute("INSERT INTO reports_client VALUES (NULL, %s, %s, NULL)", [datetime.now(),name])
            clients[name] = cursor.lastrowid
#            print("Client %s added to db"%name)
#        else:
#            print("Client %s already exists in db"%name)


    cursor.execute("SELECT client_id, timestamp, id from reports_interaction")
    interactions_hash = {}
    [interactions_hash.__setitem__(str(x[0])+"-"+x[1].isoformat(),x[2]) for x in cursor.fetchall()]#possibly change str to tuple
    pingability = {}
    [pingability.__setitem__(n.get('name'),n.get('pingable',default='N')) for n in clientsdata.findall('Client')]

    cursor.execute("SELECT id, owner, current_owner, %s, current_group, perms, current_perms, status, current_status, %s, current_to, version, current_version, current_exists, current_diff from reports_reason"%(backend.quote_name("group"),backend.quote_name("to")))
    reasons_hash = {}
    [reasons_hash.__setitem__(tuple(n[1:]),n[0]) for n in cursor.fetchall()]

    cursor.execute("SELECT id, name, kind, reason_id from reports_bad")
    bad_hash = {}
    [bad_hash.__setitem__((n[1],n[2]),(n[0],n[3])) for n in cursor.fetchall()]

    cursor.execute("SELECT id, name, kind, reason_id from reports_extra")
    extra_hash = {}
    [extra_hash.__setitem__((n[1],n[2]),(n[0],n[3])) for n in cursor.fetchall()]

    cursor.execute("SELECT id, name, kind, reason_id from reports_modified")
    modified_hash = {}
    [modified_hash.__setitem__((n[1],n[2]),(n[0],n[3])) for n in cursor.fetchall()]

    cursor.execute("SELECT id, metric, value from reports_performance")
    performance_hash = {}
    [performance_hash.__setitem__((n[1],n[2]),n[0]) for n in cursor.fetchall()]
    
    for r in statsdata.findall('.//Bad/*')+statsdata.findall('.//Extra/*')+statsdata.findall('.//Modified/*'):
        arguments = [r.get('owner', default=""), r.get('current_owner', default=""),
                     r.get('group', default=""), r.get('current_group', default=""),
                     r.get('perms', default=""), r.get('current_perms', default=""),
                     r.get('status', default=""), r.get('current_status', default=""),
                     r.get('to', default=""), r.get('current_to', default=""),
                     r.get('version', default=""), r.get('current_version', default=""),
                     eval(r.get('current_exists', default="True").capitalize()), r.get('current_diff', default="")]
        if reasons_hash.has_key(tuple(arguments)):
            current_reason_id = reasons_hash[tuple(arguments)]
#            print("Reason already exists..... It's ID is: %s"%current_reason_id)
        else:
            cursor.execute("INSERT INTO reports_reason VALUES (NULL, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);",
                           arguments)
            current_reason_id = cursor.lastrowid
            reasons_hash[tuple(arguments)] = current_reason_id
                               
#            print("Reason inserted with id %s"%current_reason_id)

    print "----------------REASONS SYNCED---------------------"
    
    for node in statsdata.findall('Node'):
        name = node.get('name')
        try:
            pingability[name]
        except KeyError:
            pingabilty[name] = 'N'
        for statistics in node.findall('Statistics'):
            t = strptime(statistics.get('time'))
            timestamp = datetime(t[0],t[1],t[2],t[3],t[4],t[5])
            if interactions_hash.has_key(str(clients[name]) +"-"+ timestamp.isoformat()):
                current_interaction_id = interactions_hash[str(clients[name])+"-"+timestamp.isoformat()]
#                print("Interaction for %s at %s with id %s already exists"%(clients[name],
#                      datetime(t[0],t[1],t[2],t[3],t[4],t[5]),current_interaction_id))
            else:
                cursor.execute("INSERT INTO reports_interaction VALUES (NULL, %s, %s, %s, %s, %s, %s, %s, %s);",
                               [clients[name], timestamp,
                                statistics.get('state', default="unknown"), statistics.get('revision',default="unknown"),
                                statistics.get('client_version',default="unknown"), pingability[name],
                                statistics.get('good',default="0"), statistics.get('total',default="0")])
                current_interaction_id = cursor.lastrowid
                interactions_hash[str(clients[name])+"-"+timestamp.isoformat()] = current_interaction_id
                #print("Interaction for %s at %s with id %s INSERTED in to db"%(clients[name],
                #    timestamp, current_interaction_id))
            for (xpath, hashname, tablename) in [('Bad/*', bad_hash, 'reports_bad'),
                                                 ('Extra/*', extra_hash, 'reports_extra'),
                                                 ('Modified/*', modified_hash, 'reports_modified')]:
                for x in statistics.findall(xpath):
                    if not hashname.has_key((x.get('name'), x.tag)):
                        arguments = [x.get('owner', default=""), x.get('current_owner', default=""),
                                     x.get('group', default=""), x.get('current_group', default=""),
                                     x.get('perms', default=""), x.get('current_perms', default=""),
                                     x.get('status', default=""), x.get('current_status', default=""),
                                     x.get('to', default=""), x.get('current_to', default=""),
                                     x.get('version', default=""), x.get('current_version', default=""),
                                     eval(x.get('current_exists', default="True").capitalize()), x.get('current_diff', default="")]
                        cursor.execute("INSERT INTO "+tablename+" VALUES (NULL, %s, %s, %s);",
                                       [x.get('name'), x.tag, reasons_hash[tuple(arguments)]])
                        item_id = cursor.lastrowid
                        hashname[(x.get('name'), x.tag)] = (item_id, current_interaction_id)
                    #print "Bad item INSERTED having reason id %s and ID %s"%(hashname[(x.get('name'),x.tag)][1],
                    #                                                         hashname[(x.get('name'),x.tag)][0])                
                    else:
                        item_id = hashname[(x.get('name'), x.tag)][0]
                        #print "Bad item exists, has reason id %s and ID %s"%(hashname[(x.get('name'),x.tag)][1],
                        #                                                              hashname[(x.get('name'),x.tag)][0])
                    try:
                        cursor.execute("INSERT INTO "+tablename+"_interactions VALUES (NULL, %s, %s);",
                                       [item_id, current_interaction_id])
                    except:
                        pass

            for times in statistics.findall('OpStamps'):
                for tags in times.items():
                    if not performance_hash.has_key((tags[0],eval(tags[1]))):
                        cursor.execute("INSERT INTO reports_performance VALUES (NULL, %s, %s)",[tags[0],tags[1]])
                        performance_hash[(tags[0],tags[1])] = cursor.lastrowid
                    else:
                        item_id = performance_hash[(tags[0],eval(tags[1]))]
                        #already exists
                    try:
                        cursor.execute("INSERT INTO reports_performance_interaction VALUES (NULL, %s, %s);",
                                       [item_id, current_interaction_id])
                    except:
                        pass

                
    print("----------------INTERACTIONS SYNCED----------------")
    connection._commit()
    cursor.execute("select reports_interaction.id, x.client_id from (select client_id, MAX(timestamp) as timer from reports_interaction Group BY client_id) x, reports_interaction where reports_interaction.client_id = x.client_id AND reports_interaction.timestamp = x.timer")
    for row in cursor.fetchall():
        cursor.execute("UPDATE reports_client SET current_interaction_id = %s where reports_client.id = %s",
                       [row[0],row[1]])
        print "setting current_interaction_id for client ID %s to %s"%(row[1],row[0])

    print("------------LATEST INTERACTION SET----------------")

    #use that crazy query to update all the latest client_interaction records.
    
            
    connection._commit()
    #Clients are consistent
    for q in connection.queries:
        if not (q['sql'].startswith('INSERT INTO reports_bad_interactions')|
                q['sql'].startswith('INSERT INTO reports_extra_interactions')|
                q['sql'].startswith('INSERT INTO reports_performance_interaction')|
                q['sql'].startswith('INSERT INTO reports_modified_interactions')|
                q['sql'].startswith('UPDATE reports_client SET current_interaction_id')):
            print q

    raise SystemExit, 0


    #-------------------------------
    for node in statsdata.findall('Node'):
        (client_rec, cr_created) = Client.objects.get_or_create(name=node.get('name'),
                                        defaults={'name': node.get('name'), 'creation': datetime.now()})

        for statistics in node.findall('Statistics'):
            t = strptime(statistics.get('time'))
            (interaction_rec, ir_created) = Interaction.objects.get_or_create(client=client_rec.id,
                                                timestamp=datetime(t[0],t[1],t[2],t[3],t[4],t[5]),
                                                defaults={'client':client_rec,
                                                          'timestamp':datetime(t[0],t[1],t[2],t[3],t[4],t[5]),
                                                          'state':statistics.get('state', default="unknown"),
                                                          'repo_revision':statistics.get('revision', default="unknown"),
                                                          'client_version':statistics.get('client_version'),
                                                          'goodcount':statistics.get('good', default="unknown"),
                                                          'totalcount':statistics.get('total', default="unknown")})
            for bad in statistics.findall('Bad'):
                for ele in bad.getchildren():
                    (reason_rec, rr_created) = Reason.objects.get_or_create(owner=ele.get('owner',default=''),
                                                        current_owner=ele.get('current_owner',default=''),
                                                        group=ele.get('group',default=''),
                                                        current_group=ele.get('current_group',default=''),
                                                        perms=ele.get('perms',default=''),
                                                        current_perms=ele.get('current_perms',default=''),
                                                        status=ele.get('status',default=''),
                                                        current_status=ele.get('current_status',default=''),
                                                        to=ele.get('to',default=''),
                                                        current_to=ele.get('current_to',default=''),
                                                        version=ele.get('version',default=''),
                                                        current_version=ele.get('current_version',default=''),
                                                        current_exists=ele.get('current_exists',default='True'),
                                                        current_diff=ele.get('current_diff',default=''),
                                                        defaults={'owner':ele.get('owner',default=''),
                                                                  'current_owner':ele.get('current_owner',default=''),
                                                                  'group':ele.get('group',default=''),
                                                                  'current_group':ele.get('current_group',default=''),
                                                                  'perms':ele.get('perms',default=''),
                                                                  'current_perms':ele.get('current_perms',default=''),
                                                                  'status':ele.get('status',default=''),
                                                                  'current_status':ele.get('current_status',default=''),
                                                                  'to':ele.get('to',default=''),
                                                                  'current_to':ele.get('current_to',default=''),
                                                                  'version':ele.get('version',default=''),
                                                                  'current_version':ele.get('current_version',default=''),
                                                                  'current_exists':ele.get('current_exists',default='True'),
                                                                  'current_diff':ele.get('current_diff',default='')})
                        

                    (ele_rec, er_created) = Bad.objects.get_or_create(name=ele.get('name'), kind=ele.tag,
                                                defaults={'name':ele.get('name'),
                                                          'kind':ele.tag,
                                                          'reason':reason_rec})

                    if not ele_rec in interaction_rec.bad_items.all():
                        interaction_rec.bad_items.add(ele_rec)

            for modified in statistics.findall('Modified'):
                for ele in modified.getchildren():
                    (reason_rec, rr_created) = Reason.objects.get_or_create(owner=ele.get('owner',default=''),
                                                        current_owner=ele.get('current_owner',default=''),
                                                        group=ele.get('group',default=''),
                                                        current_group=ele.get('current_group',default=''),
                                                        perms=ele.get('perms',default=''),
                                                        current_perms=ele.get('current_perms',default=''),
                                                        status=ele.get('status',default=''),
                                                        current_status=ele.get('current_status',default=''),
                                                        to=ele.get('to',default=''),
                                                        current_to=ele.get('current_to',default=''),
                                                        version=ele.get('version',default=''),
                                                        current_version=ele.get('current_version',default=''),
                                                        current_exists=ele.get('current_exists',default='True'),
                                                        current_diff=ele.get('current_diff',default=''),
                                                        defaults={'owner':ele.get('owner',default=''),
                                                                  'current_owner':ele.get('current_owner',default=''),
                                                                  'group':ele.get('group',default=''),
                                                                  'current_group':ele.get('current_group',default=''),
                                                                  'perms':ele.get('perms',default=''),
                                                                  'current_perms':ele.get('current_perms',default=''),
                                                                  'status':ele.get('status',default=''),
                                                                  'current_status':ele.get('current_status',default=''),
                                                                  'to':ele.get('to',default=''),
                                                                  'current_to':ele.get('current_to',default=''),
                                                                  'version':ele.get('version',default=''),
                                                                  'current_version':ele.get('current_version',default=''),
                                                                  'current_exists':ele.get('current_exists',default='True'),
                                                                  'current_diff':ele.get('current_diff',default='')})
                        

                    (ele_rec, er_created) = Modified.objects.get_or_create(name=ele.get('name'), kind=ele.tag,
                                                defaults={'name':ele.get('name'),
                                                          'kind':ele.tag,
                                                          'reason':reason_rec})
                    if not ele_rec in interaction_rec.modified_items.all():
                        interaction_rec.modified_items.add(ele_rec)

            for extra in statistics.findall('Extra'):
                for ele in extra.getchildren():
                    (reason_rec, rr_created) = Reason.objects.get_or_create(owner=ele.get('owner',default=''),
                                                        current_owner=ele.get('current_owner',default=''),
                                                        group=ele.get('group',default=''),
                                                        current_group=ele.get('current_group',default=''),
                                                        perms=ele.get('perms',default=''),
                                                        current_perms=ele.get('current_perms',default=''),
                                                        status=ele.get('status',default=''),
                                                        current_status=ele.get('current_status',default=''),
                                                        to=ele.get('to',default=''),
                                                        current_to=ele.get('current_to',default=''),
                                                        version=ele.get('version',default=''),
                                                        current_version=ele.get('current_version',default=''),
                                                        current_exists=ele.get('current_exists',default='True'),
                                                        current_diff=ele.get('current_diff',default=''),
                                                        defaults={'owner':ele.get('owner',default=''),
                                                                  'current_owner':ele.get('current_owner',default=''),
                                                                  'group':ele.get('group',default=''),
                                                                  'current_group':ele.get('current_group',default=''),
                                                                  'perms':ele.get('perms',default=''),
                                                                  'current_perms':ele.get('current_perms',default=''),
                                                                  'status':ele.get('status',default=''),
                                                                  'current_status':ele.get('current_status',default=''),
                                                                  'to':ele.get('to',default=''),
                                                                  'current_to':ele.get('current_to',default=''),
                                                                  'version':ele.get('version',default=''),
                                                                  'current_version':ele.get('current_version',default=''),
                                                                  'current_exists':ele.get('current_exists',default='True'),
                                                                  'current_diff':ele.get('current_diff',default='')})
                        

                    (ele_rec, er_created) = Extra.objects.get_or_create(name=ele.get('name'), kind=ele.tag,
                                                defaults={'name':ele.get('name'),
                                                          'kind':ele.tag,
                                                          'reason':reason_rec})
                        
                    if not ele_rec in interaction_rec.extra_items.all():
                        interaction_rec.extra_items.add(ele_rec)

            for times in statistics.findall('OpStamps'):
                for tags in times.items():
                    (time_rec, tr_created) = Performance.objects.get_or_create(metric=tags[0], value=tags[1],
                                                    defaults={'metric':tags[0],
                                                              'value':tags[1]})
                    if not ele_rec in interaction_rec.extra_items.all():
                        interaction_rec.performance_items.add(time_rec)

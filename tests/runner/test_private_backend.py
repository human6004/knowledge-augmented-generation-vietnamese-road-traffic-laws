import copy
import unittest
from unittest.mock import patch, Mock
import kag.backend_identity as identity


class PrivateBackendTests(unittest.TestCase):
    def setUp(self):
        self.project='kag-s8-new'
        network={'NetworkID':'network-id','IPAddress':'172.30.0.3','Aliases':['openspg-neo4j']}
        self.server={'Id':'server-id','Image':'server-image','State':{'Running':True},
            'Config':{'Labels':{'com.docker.compose.project':self.project,'com.docker.compose.service':'openspg-server'}},
            'Mounts':[], 'NetworkSettings':{'Networks':{self.project+'_private':dict(network,IPAddress='172.30.0.2')}}}
        self.database={'Id':'database-id','Image':'database-image','State':{'Running':True},
            'Config':{'Labels':{'com.docker.compose.project':self.project,'com.docker.compose.service':'openspg-neo4j'}},
            'Mounts':[{'Type':'volume','Name':self.project+'_openspg-neo4j-data','Destination':'/data'},
                      {'Type':'volume','Name':self.project+'_openspg-neo4j-logs','Destination':'/logs'}],
            'NetworkSettings':{'Networks':{self.project+'_private':network}}}
        self.runtime={'Id':'runner-id','State':{'Running':True},'HostConfig':{'NetworkMode':'container:server-id'}}
        self.store={'uri':'bolt://openspg-neo4j:7687','database':'freshsample20261011','user':'neo4j','password':'fixture'}

    def transport(self, **kwargs):
        self.assertTrue(hasattr(identity,'DockerPrivateBackendTransport'),'private backend transport missing')
        transport=identity.DockerPrivateBackendTransport(self.project,'server-id','database-id','runner-id',**kwargs)
        records={'server-id':self.server,'database-id':self.database,'runner-id':self.runtime}
        transport._inspect=lambda key:copy.deepcopy(records[key])
        return transport

    def read(self, **kwargs):
        transport=self.transport(**kwargs)
        from kag.verify import Neo4jReadClient
        verifier=Neo4jReadClient('http://openspg-neo4j:7474','freshsample20261011',username='neo4j',password='fixture',timeout=10)
        metadata={'name':'freshsample20261011','databaseID':'new-db','serverID':'new-server','currentStatus':'online'}
        with patch.object(Neo4jReadClient,'database_metadata',return_value=metadata),patch('socket.getaddrinfo',return_value=[(None,None,None,None,('172.30.0.3',7687))]):
            return transport.read(self.store,verifier)

    def test_private_backend_attests_exact_new_volume(self):
        metadata,runtime=self.read()
        self.assertEqual(runtime,('server-id','server-image','database-id','database-image','network-id','kag-s8-new_openspg-neo4j-data'))
        self.assertEqual(metadata['databaseID'],'new-db')

    def test_private_backend_denies_legacy_volume(self):
        self.database['Mounts'][0]['Name']='kag-legal-neo4j-data'
        with self.assertRaises(identity.BackendIdentityError):self.read()

    def test_private_backend_denies_other_runtime_namespace(self):
        self.runtime['HostConfig']['NetworkMode']='container:legacy-id'
        with self.assertRaises(identity.BackendIdentityError):self.read()

    def test_private_backend_denies_cross_project_server(self):
        self.server['Config']['Labels']['com.docker.compose.project']='docker'
        with self.assertRaises(identity.BackendIdentityError):self.read()

    def test_private_backend_attests_only_exact_revised_volume(self):
        self.database['Mounts'][0]['Name']='kag-s8-new_openspg-neo4j-data-fresh-phase-b'
        try: _,runtime=self.read(storage_revision='-fresh-phase-b')
        except TypeError:self.fail('Private transport must support its explicitly bound storage revision')
        self.assertEqual(runtime[-1],'kag-s8-new_openspg-neo4j-data-fresh-phase-b')
        for volume in ('kag-s8-new_openspg-neo4j-data','kag-s8-new_openspg-neo4j-data-fresh-other',
                       'docker_openspg-neo4j-data-fresh-phase-b'):
            self.database['Mounts'][0]['Name']=volume
            with self.subTest(volume=volume),self.assertRaises(identity.BackendIdentityError):
                self.read(storage_revision='-fresh-phase-b')

    def test_private_backend_denies_unsafe_storage_revision_before_inspection(self):
        for revision in (None,1,'fresh-phase-b','-fresh-','-fresh-A','-fresh-../x','-fresh-'+'a'*41):
            with self.subTest(revision=revision),patch.object(identity.DockerPrivateBackendTransport,'_inspect') as inspect:
                try:
                    with self.assertRaises(identity.BackendIdentityError):
                        self.transport(storage_revision=revision)
                except TypeError:self.fail('Storage revision must be validated by the private transport')
                inspect.assert_not_called()

    def test_inspect_uses_only_get_and_closes_local_socket(self):
        key='a'*64
        transport=identity.DockerPrivateBackendTransport(self.project,key,'b'*64,'c'*64)
        response=Mock(status=200);response.read.return_value=b'{"Id":"fixture"}'
        with patch('socket.socket') as socket,patch('http.client.HTTPConnection.request',autospec=True) as request, \
                patch('http.client.HTTPConnection.getresponse',return_value=response):
            request.side_effect=lambda connection,*args:connection.connect()
            self.assertEqual(transport._inspect(key),{'Id':'fixture'})
            self.assertEqual(request.call_args.args[1:],('GET','/containers/'+key+'/json'))
            self.assertEqual(request.call_count,1)
            socket.return_value.connect.assert_called_once_with('/var/run/docker.sock')
            socket.return_value.close.assert_called_once()
        with patch('socket.socket') as socket:
            for invalid in ('short','a'*63,'A'*64,'a'*64+'/exec'):
                with self.subTest(invalid=invalid),self.assertRaises(identity.BackendIdentityError):
                    transport._inspect(invalid)
            socket.assert_not_called()
        with patch('http.client.HTTPConnection.request'), \
                patch('http.client.HTTPConnection.getresponse',return_value=Mock(status=403)):
            with self.assertRaises(identity.BackendIdentityError):transport._inspect(key)

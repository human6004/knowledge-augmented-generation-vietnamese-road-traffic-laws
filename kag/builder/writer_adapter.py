"""Small, fail-closed adapter from validated C2 graph specs to pinned KAG writer."""
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import ipaddress
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
from typing import Any

from kag.builder.codec import BuilderContractError, canonical_json, decode_properties
from kag.builder.mapping import application_edge_key
from kag.builder.production_scope import (ProductionSettings, ProductionScope,
    SAMPLE_PROJECT_ID, validate_production_scope, _PRODUCTION_PROOF)
from kag.builder.model.sub_graph import Edge, Node, SubGraph
from kag.builder.component.writer.kg_writer import AlterOperationEnum, KGWriter
from knext.graph.client import GraphClient


class WriterAdapterError(ValueError):
    """A graph spec or target is outside the C4.1 writer contract."""


class NodeReadbackError(WriterAdapterError):
    """The node-stage readback barrier did not prove the requested state."""


@dataclass(frozen=True)
class _ContractContext:
    namespace: str
    contract: Mapping[str, Any]
    synthetic_prefix: str = 'C4_1_SMOKE_'


_SMOKE_PROJECT_PROOF = object()
_MANIFEST_PROJECT_PROOF = object()
_C43A_POLICY = {
    'project_id': SAMPLE_PROJECT_ID, 'project_name': 'VietRoadTrafficC43A10Pct',
    'namespace': 'VietRoadTraffic', 'partition': 5, 'nodes': 7495, 'edges': 8180,
    'nodes_sha256': 'fe61563daad7cf4f331b4f8c44a327365e07fe187436cc939b21c603ec6c25ff',
    'edges_sha256': 'c5587eb118b3ba3f9a51b17539e773c4624447bc404de3a2a639842886661874',
}


@dataclass(frozen=True)
class _ManifestScope:
    path: Path
    file_sha256: str
    node_keys: frozenset[tuple[str, str]]
    edge_tuples: frozenset[tuple[str, ...]]
    _proof: object = field(repr=False, compare=False)

    def verify_file(self) -> None:
        try:
            digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
        except OSError:
            raise WriterAdapterError('authoritative sample manifest cannot be read') from None
        if self._proof is not _MANIFEST_PROJECT_PROOF or digest != self.file_sha256:
            raise WriterAdapterError('authoritative sample manifest changed after scope discovery')


@dataclass(frozen=True)
class _VerifiedSmokeProject:
    project_id: int
    project_name: str
    namespace: str
    host_addr: str
    _proof: object = field(repr=False, compare=False)


@dataclass(frozen=True)
class WriterConfig:
    """Explicit localhost settings bound to server-verified smoke-project metadata."""

    host_addr: str
    project: _VerifiedSmokeProject
    namespace: str
    contract: Mapping[str, Any]
    synthetic_prefix: str = 'C4_1_SMOKE_'
    scope: str = 'DENY'
    manifest_scope: _ManifestScope | None = None
    production_scope: ProductionScope | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.project, _VerifiedSmokeProject):
            raise WriterAdapterError('project must come from verified OpenSPG project discovery')
        if self.scope == 'PRODUCTION':
            if not isinstance(self.production_scope, ProductionScope) or self.manifest_scope is not None:
                raise WriterAdapterError('production requires verified C3 scope, never a sample manifest')
            self.production_scope.verify_files(self.contract)
            settings = self.production_scope.settings
            if (self.host_addr, self.project_id, self.project_name, self.namespace) != (
                    settings.host_addr, settings.expected_project_id, settings.project_name, settings.namespace):
                raise WriterAdapterError('production configuration differs from verified target')
        else:
            _validate_local_host(self.host_addr)
            if self.production_scope is not None:
                raise WriterAdapterError('sample scope cannot carry production proof')
        proof = {'C4_1_SMOKE': _SMOKE_PROJECT_PROOF,
                 'C4_3A_MANIFEST_SAMPLE': _MANIFEST_PROJECT_PROOF,
                 'PRODUCTION': _PRODUCTION_PROOF}.get(self.scope)
        if (proof is None
                or not isinstance(self.project, _VerifiedSmokeProject)
                or self.project._proof is not proof):
            raise WriterAdapterError('project must come from verified OpenSPG smoke-project discovery')
        if self.project.host_addr != self.host_addr:
            raise WriterAdapterError('verified smoke project belongs to a different OpenSPG host')
        if type(self.project.project_id) is not int or self.project.project_id <= 0:
            raise WriterAdapterError('verified project ID must be a positive native int')
        if self.scope == 'C4_1_SMOKE' and not self.project.project_name.startswith('C4_1_SMOKE_'):
            raise WriterAdapterError('project metadata does not identify a dedicated C4_1_SMOKE_ knowledge base')
        if not isinstance(self.namespace, str) or not self.namespace.strip():
            raise WriterAdapterError('namespace must be nonblank Text')
        if self.contract.get('namespace') != self.namespace:
            raise WriterAdapterError('namespace differs from the supplied schema contract')
        if self.project.namespace != self.namespace:
            raise WriterAdapterError('verified project namespace differs from the schema contract')
        _validate_prefix(self.synthetic_prefix)
        if self.scope == 'C4_1_SMOKE':
            if self.manifest_scope is not None:
                raise WriterAdapterError('C4.1 smoke scope cannot carry a real sample manifest')
        elif self.scope == 'C4_3A_MANIFEST_SAMPLE':
            if ((self.project_id, self.project_name, self.namespace) !=
                    (_C43A_POLICY['project_id'], _C43A_POLICY['project_name'], _C43A_POLICY['namespace'])
                    or not isinstance(self.manifest_scope, _ManifestScope)):
                raise WriterAdapterError('C4.3a requires its exact verified project and manifest scope')
            self.manifest_scope.verify_file()

    @property
    def project_id(self) -> int:
        return self.project.project_id

    @property
    def project_name(self) -> str:
        return self.project.project_name


def _validate_local_host(host_addr: str) -> None:
    parsed = urlsplit(host_addr)
    host = (parsed.hostname or '').lower()
    try:
        local = host == 'localhost' or ipaddress.ip_address(host).is_loopback
    except ValueError:
        local = False
    if (parsed.scheme not in ('http', 'https') or not local or parsed.username
            or parsed.password or parsed.query or parsed.fragment):
        raise WriterAdapterError('C4.1 writer accepts only an explicit localhost HTTP(S) host')


def discover_smoke_project(project_client: Any, project_id: int, project_name: str,
                           host_addr: str, contract: Mapping[str, Any]) -> _VerifiedSmokeProject:
    """Read server metadata; only an exact dedicated name/ID/namespace becomes writable."""
    _validate_local_host(host_addr)
    if type(project_id) is not int or project_id <= 0:
        raise WriterAdapterError('project discovery requires a positive native int ID')
    if not isinstance(project_name, str) or not project_name.startswith('C4_1_SMOKE_'):
        raise WriterAdapterError('expected project name must start C4_1_SMOKE_')
    if getattr(project_client, '_host_addr', None) != host_addr:
        raise WriterAdapterError('project discovery client is not bound to the configured localhost host')
    try:
        record = project_client.get(id=project_id)
    except Exception:
        raise WriterAdapterError('OpenSPG smoke-project discovery failed') from None
    actual_id = getattr(record, 'id', None)
    actual_name = getattr(record, 'name', None)
    actual_namespace = getattr(record, 'namespace', None)
    if isinstance(record, Mapping):
        actual_id = record.get('id', actual_id)
        actual_name = record.get('name', actual_name)
        actual_namespace = record.get('namespace', actual_namespace)
    if (type(actual_id) not in (int, str) or str(actual_id) != str(project_id) or actual_name != project_name
            or actual_namespace != contract.get('namespace')):
        raise WriterAdapterError('OpenSPG project metadata does not match the dedicated smoke target')
    return _VerifiedSmokeProject(project_id, actual_name, actual_namespace, host_addr,
                                 _SMOKE_PROJECT_PROOF)


def _validate_prefix(prefix: str) -> None:
    if (not isinstance(prefix, str) or not prefix.startswith('C4_1_SMOKE_')
            or prefix.strip() != prefix
            or any(char in prefix for char in '*?[]%')):
        raise WriterAdapterError('synthetic prefix must start C4_1_SMOKE_ and contain no wildcards')


def discover_manifest_project(project_client: Any, host_addr: str, contract: Mapping[str, Any],
                              manifest_path: str | Path, node_specs: Sequence[Mapping[str, Any]],
                              edge_specs: Sequence[Mapping[str, Any]]) -> WriterConfig:
    """Grant only the pinned C4.3a project and the exact fixed manifest identities."""
    _validate_local_host(host_addr)
    if (getattr(project_client, '_host_addr', None) != host_addr
            or contract.get('namespace') != _C43A_POLICY['namespace']):
        raise WriterAdapterError('manifest discovery target differs from C4.3a policy')
    try:
        record = project_client.get(id=_C43A_POLICY['project_id'])
        values = tuple(record.get(key) if isinstance(record, Mapping) else getattr(record, key, None)
                       for key in ('id', 'name', 'namespace'))
        expected = tuple(_C43A_POLICY[key] for key in ('project_id', 'project_name', 'namespace'))
        if (type(values[0]) not in (int, str) or str(values[0]) != str(expected[0])
                or values[1:] != expected[1:]):
            raise WriterAdapterError('server project metadata does not match exact C4.3a target')
        values = (expected[0], *values[1:])  # pinned SDK exposes Project.id as Text
        path = Path(manifest_path).resolve()
        raw = path.read_bytes()
        manifest = json.loads(raw)
        pins = ((manifest['chosen_partition'], 'partition'),
                (manifest['counts_by_type']['total'], 'nodes'), (manifest['total_edges'], 'edges'),
                (manifest['selected_node_identity_sha256'], 'nodes_sha256'),
                (manifest['selected_edge_tuple_sha256'], 'edges_sha256'))
        if any(type(value) is not type(_C43A_POLICY[key]) or value != _C43A_POLICY[key]
               for value, key in pins):
            raise WriterAdapterError('sample manifest partition, hashes or counts differ from C4.3a policy')
        node_keys = [(node['type'], node['id']) for node in node_specs]
        edge_tuples = [tuple(edge['tuple']) for edge in edge_specs]
        if (len(node_keys) != _C43A_POLICY['nodes'] or len(set(node_keys)) != len(node_keys)
                or len(edge_tuples) != _C43A_POLICY['edges'] or len(set(edge_tuples)) != len(edge_tuples)):
            raise WriterAdapterError('sample actual counts or uniqueness differ from C4.3a policy')
        node_text = ''.join('\t'.join(key) + '\n' for key in sorted(node_keys))
        edge_text = ''.join(canonical_json(key) + '\n' for key in sorted(edge_tuples))
        if (hashlib.sha256(node_text.encode('utf-8')).hexdigest() != _C43A_POLICY['nodes_sha256']
                or hashlib.sha256(edge_text.encode('utf-8')).hexdigest() != _C43A_POLICY['edges_sha256']):
            raise WriterAdapterError('actual sample identities or edge tuples do not match manifest hashes')
        allowed_nodes = frozenset(node_keys)
        if any(len(t) != 5 or (t[0], t[1]) not in allowed_nodes or (t[3], t[4]) not in allowed_nodes
               for t in edge_tuples):
            raise WriterAdapterError('manifest edge endpoint is outside selected nodes')
    except WriterAdapterError:
        raise
    except Exception:
        raise WriterAdapterError('C4.3a project or authoritative manifest discovery failed') from None
    scope = _ManifestScope(path, hashlib.sha256(raw).hexdigest(), allowed_nodes,
                           frozenset(edge_tuples), _MANIFEST_PROJECT_PROOF)
    project = _VerifiedSmokeProject(*values, host_addr, _MANIFEST_PROJECT_PROOF)
    return WriterConfig(host_addr, project, contract['namespace'], contract,
                        scope='C4_3A_MANIFEST_SAMPLE', manifest_scope=scope)


def discover_production_project(project_client: Any, settings: ProductionSettings,
                                contract: Mapping[str, Any], manifest_path: str | Path,
                                *, project_root: str | Path | None = None) -> WriterConfig:
    """Validate offline first, resolve exact name+namespace, then independently verify ID."""
    scope = validate_production_scope(settings, contract, manifest_path, project_root=project_root)
    if getattr(project_client, '_host_addr', None) != settings.host_addr:
        raise WriterAdapterError('production project client belongs to a different OpenSPG host')
    def fields(record):
        return tuple(record.get(k) if isinstance(record, Mapping) else getattr(record, k, None)
                     for k in ('id', 'name', 'namespace'))
    try:
        # ProjectClient.get picks the first match; get_all collapses namespaces.
        records = project_client._rest_client.project_get()
        matches = [fields(r) for r in records
                   if fields(r)[1:] == (settings.project_name, settings.namespace)]
        if len(matches) != 1:
            raise WriterAdapterError('production discovery requires exactly one name+namespace match')
        actual_id, name, namespace = matches[0]
        if (type(actual_id) not in (int, str)
                or str(actual_id) != str(settings.expected_project_id)):
            raise WriterAdapterError('resolved production project ID differs from explicit expected ID')
        verified = fields(project_client.get(id=settings.expected_project_id))
        if (type(verified[0]) not in (int, str)
                or str(verified[0]) != str(settings.expected_project_id)
                or verified[1:] != (name, namespace)):
            raise WriterAdapterError('returned production project ID/name/namespace verification failed')
    except WriterAdapterError:
        raise
    except Exception:
        raise WriterAdapterError('production project discovery failed') from None
    project = _VerifiedSmokeProject(settings.expected_project_id, name, namespace,
                                     settings.host_addr, _PRODUCTION_PROOF)
    return WriterConfig(settings.host_addr, project, settings.namespace, contract,
                        scope='PRODUCTION', production_scope=scope)


def _context(contract: Mapping[str, Any] | WriterConfig, prefix: str | None = None):
    if isinstance(contract, WriterConfig):
        return contract
    if not isinstance(contract, Mapping) or not isinstance(contract.get('namespace'), str):
        raise WriterAdapterError('schema contract must declare a namespace')
    return _ContractContext(contract['namespace'], contract,
                            prefix if prefix is not None else 'C4_1_SMOKE_')


def _local_type_name(type_name: str, namespace: str, allowed: Sequence[str]) -> str:
    if not isinstance(type_name, str) or not type_name.startswith(namespace + '.'):
        raise WriterAdapterError(f'type must be fully qualified in namespace {namespace!r}')
    local_name = type_name[len(namespace) + 1:]
    if not local_name or '.' in local_name or local_name not in allowed:
        raise WriterAdapterError(f'unknown graph type {type_name!r}')
    return local_name


def _physical_properties(values: Any, rows: Sequence[Mapping[str, Any]], context: str) -> dict[str, Any]:
    if not isinstance(values, Mapping):
        raise WriterAdapterError(f'{context}: properties must be a mapping')
    declared = {row['schema_name'] for row in rows}
    unknown = {key for key in values if key not in declared and not (isinstance(key, str) and key.startswith('_'))}
    if unknown:
        raise WriterAdapterError(f'{context}: undeclared properties {sorted(unknown)!r}')
    return {key: value for key, value in values.items() if value is not None}


def _validate_node(spec: Mapping[str, Any], config: WriterConfig | _ContractContext) -> tuple[str, str, str, dict[str, Any]]:
    try:
        type_name, identity, name = spec['type'], spec['id'], spec['name']
        local_type = _local_type_name(type_name, config.namespace, config.contract['node_types'])
        rows = config.contract['node_properties'][local_type]
        props = _physical_properties(spec.get('properties', {}), rows, f'node {identity!r}')
        if not isinstance(identity, str) or not identity.strip() or name != identity:
            raise WriterAdapterError('node id/name must be the same nonblank exact Text')
        if props.get('id', identity) != identity or props.get('name', name) != name:
            raise WriterAdapterError('node properties id/name conflict with graph identity')
        physical = dict(props, id=identity, name=name)
        decode_properties(physical, rows, server_encoded=False)
        props.pop('id', None)
        props.pop('name', None)
        return type_name, identity, name, props
    except (KeyError, TypeError, BuilderContractError) as exc:
        if isinstance(exc, WriterAdapterError):
            raise
        raise WriterAdapterError(f'invalid node spec: {exc}') from exc


def _validate_edge(spec: Mapping[str, Any], config: WriterConfig | _ContractContext) -> tuple[tuple[str, ...], str, dict[str, Any]]:
    try:
        edge_tuple = tuple(spec['tuple'])
        if len(edge_tuple) != 5 or any(not isinstance(value, str) or not value.strip()
                                       for value in edge_tuple):
            raise WriterAdapterError('edge tuple must contain five nonblank Text fields')
        from_type, from_id, predicate, to_type, to_id = edge_tuple
        relations = config.contract['relations']
        from_local = _local_type_name(from_type, config.namespace, config.contract['node_types'])
        to_local = _local_type_name(to_type, config.namespace, config.contract['node_types'])
        relation = relations.get(predicate)
        if not relation or (relation['from_type'], relation['to_type']) != (from_local, to_local):
            raise WriterAdapterError(f'edge endpoint types do not match predicate {predicate!r}')
        key = application_edge_key(edge_tuple)
        if spec.get('application_edge_key') != key:
            raise WriterAdapterError('application_edge_key does not match the C2 tuple key')
        rows = config.contract['relation_properties'][predicate]
        props = _physical_properties(spec.get('properties', {}), rows, f'edge {key}')
        decode_properties(props, rows, server_encoded=False)
        return edge_tuple, key, props
    except (KeyError, TypeError, BuilderContractError) as exc:
        if isinstance(exc, WriterAdapterError):
            raise
        raise WriterAdapterError(f'invalid edge spec: {exc}') from exc


def to_subgraphs(
    specs: Sequence[Mapping[str, Any]], batch_size: int, stage: str,
    contract: Mapping[str, Any] | WriterConfig,
) -> list[SubGraph]:
    """Convert ordered C2 physical specs to deterministic node-only or edge-only batches."""
    if type(batch_size) is not int or batch_size < 1:
        raise WriterAdapterError('batch_size must be a positive native int')
    if stage not in ('nodes', 'edges'):
        raise WriterAdapterError("stage must be 'nodes' or 'edges'")
    if not isinstance(specs, Sequence) or isinstance(specs, (str, bytes)):
        raise WriterAdapterError('specs must be an ordered sequence')
    config = _context(contract)

    converted = []
    if stage == 'nodes':
        for spec in specs:
            type_name, identity, name, props = _validate_node(spec, config)
            converted.append(Node(_id=identity, name=name, label=type_name, properties=props))
    else:
        for spec in specs:
            edge_tuple, edge_key, props = _validate_edge(spec, config)
            from_type, from_id, predicate, to_type, to_id = edge_tuple
            from_node = Node(_id=from_id, name=from_id, label=from_type, properties={})
            to_node = Node(_id=to_id, name=to_id, label=to_type, properties={})
            converted.append(Edge(_id=edge_key, from_node=from_node, to_node=to_node,
                                  label=predicate, properties=props))

    return [SubGraph(converted[offset:offset + batch_size] if stage == 'nodes' else [],
                     converted[offset:offset + batch_size] if stage == 'edges' else [])
            for offset in range(0, len(converted), batch_size)]


class NativeIntegerKGWriter(KGWriter):
    """Pinned KGWriter normalization with exact schema-declared Integer restoration."""

    def __init__(self, config: WriterConfig, graph_client: Any = None):
        if not isinstance(config, WriterConfig):
            raise WriterAdapterError('an explicit WriterConfig is required')
        if config.scope == 'PRODUCTION':
            config.__post_init__()
        # KGWriter.__init__ resolves implicit global KAG config. Keep these exact
        # upstream attributes explicit so the same pinned _invoke/normalizer runs.
        self.config = config
        self.kag_project_config = config
        self.project_id = config.project_id
        self.client = graph_client if graph_client is not None else GraphClient(
            host_addr=config.host_addr, project_id=config.project_id)
        _check_client_target(self.client, config, 'GraphClient')
        self.delete = False
        self._verified_node_keys: set[tuple[str, str]] = set()

    @property
    def checkpointer(self):
        """Every scoped invocation must reach its live scope/readback guard."""
        return None

    def standarlize_graph(self, graph):  # spelling matches the pinned upstream API
        node_restore: dict[tuple[str, str], dict[str, int]] = {}
        edge_restore: dict[str, dict[str, int]] = {}
        for node in graph.nodes:
            local = node.label.rsplit('.', 1)[-1]
            rows = self.config.contract['node_properties'].get(local, ())
            integer_names = {row['schema_name'] for row in rows
                             if row['contract_type'] in ('INTEGER', 'OPTIONAL_INTEGER')}
            values = {}
            for name in integer_names & node.properties.keys():
                value = node.properties[name]
                if value is None:
                    node.properties.pop(name)
                elif type(value) is not int:
                    raise WriterAdapterError(f'{local}.{name}: expected native int, got {type(value).__name__}')
                else:
                    values[name] = value
            node_restore[(self.format_label(node.label), node.id)] = values
        for edge in graph.edges:
            rows = self.config.contract['relation_properties'].get(edge.label, ())
            integer_names = {row['schema_name'] for row in rows
                             if row['contract_type'] in ('INTEGER', 'OPTIONAL_INTEGER')}
            values = {}
            for name in integer_names & edge.properties.keys():
                value = edge.properties[name]
                if value is None:
                    edge.properties.pop(name)
                elif type(value) is not int:
                    raise WriterAdapterError(f'{edge.label}.{name}: expected native int, got {type(value).__name__}')
                else:
                    values[name] = value
            edge_restore[edge.id] = values

        graph = super().standarlize_graph(graph)
        for node in graph.nodes:
            node.properties.update(node_restore.get((node.label, node.id), {}))
        for edge in graph.edges:
            edge.properties.update(edge_restore.get(edge.id, {}))
        return graph

    def write_subgraph(self, graph: SubGraph, stage: str) -> None:
        if stage not in ('nodes', 'edges'):
            raise WriterAdapterError("stage must be 'nodes' or 'edges'")
        if stage == 'nodes' and graph.edges or stage == 'edges' and graph.nodes:
            raise WriterAdapterError(f'{stage} batch contains objects from the other stage')
        self._invoke(graph, alter_operation=AlterOperationEnum.Upsert, lead_to_builder=False)

    def _invoke(self, input: SubGraph, alter_operation=AlterOperationEnum.Upsert,
                lead_to_builder: bool = False, **kwargs):
        """One scope gate also covers inherited invoke/ainvoke entry points."""
        _check_client_target(self.client, self.config, 'GraphClient')
        deleting = self.delete or getattr(alter_operation, 'value', alter_operation) == 'DELETE'
        _check_writer_scope(input, self.config, deleting=deleting)
        if input.nodes and input.edges:
            raise WriterAdapterError('writer requires explicit node-only or edge-only stages')
        if input.edges and not deleting:
            if (self.config.scope == 'PRODUCTION'
                    and self._verified_node_keys != self.config.production_scope.node_keys):
                raise WriterAdapterError('production edges require full C3 node readback barrier')
            if (self.config.scope == 'C4_3A_MANIFEST_SAMPLE'
                    and self._verified_node_keys != self.config.manifest_scope.node_keys):
                raise WriterAdapterError('C4.3a edges require full manifest node readback barrier')
            missing = {(edge.from_type, edge.from_id) for edge in input.edges
                       if (edge.from_type, edge.from_id) not in self._verified_node_keys}
            missing.update((edge.to_type, edge.to_id) for edge in input.edges
                           if (edge.to_type, edge.to_id) not in self._verified_node_keys)
            if missing:
                raise WriterAdapterError('edge write requires successful readback of every endpoint node')
        self._verified_node_keys.difference_update((node.label, node.id) for node in input.nodes)
        return super()._invoke(input, alter_operation=alter_operation,
                               lead_to_builder=lead_to_builder, **kwargs)

    def delete_subgraph(self, graph: SubGraph, stage: str) -> None:
        if stage not in ('nodes', 'edges'):
            raise WriterAdapterError("stage must be 'nodes' or 'edges'")
        if stage == 'nodes' and graph.edges or stage == 'edges' and graph.nodes:
            raise WriterAdapterError(f'{stage} delete batch contains objects from the other stage')
        _check_writer_scope(graph, self.config, deleting=True)
        self._verified_node_keys.difference_update((node.label, node.id) for node in graph.nodes)
        self._invoke(graph, alter_operation=AlterOperationEnum.Delete, lead_to_builder=False)

    def _mark_nodes_verified(self, nodes: Sequence[Mapping[str, Any]]) -> None:
        self._verified_node_keys.update((node['type'], node['id']) for node in nodes)


def _check_writer_scope(graph: SubGraph, config: WriterConfig, *, deleting: bool = False) -> None:
    config.__post_init__()
    if config.scope == 'PRODUCTION':
        if deleting:
            raise WriterAdapterError('production scope does not authorize deletion')
        nodes = [{'type': n.label, 'id': n.id, 'name': n.name, 'properties': n.properties}
                 for n in graph.nodes]
        edges = [{'tuple': (e.from_type, e.from_id, e.label, e.to_type, e.to_id),
                  'application_edge_key': e.id, 'properties': e.properties} for e in graph.edges]
        config.production_scope.validate_specs(nodes, edges, require_vectors=True)
        for spec in nodes:
            _validate_node(spec, config)
        for spec in edges:
            _validate_edge(spec, config)
        return
    if config.scope == 'C4_3A_MANIFEST_SAMPLE':
        config.manifest_scope.verify_file()
        if deleting:
            raise WriterAdapterError('C4.3a manifest scope does not authorize deletion')
        if any((node.label, node.id) not in config.manifest_scope.node_keys for node in graph.nodes):
            raise WriterAdapterError('writer refused node outside the exact sample manifest')
        if any((edge.from_type, edge.from_id, edge.label, edge.to_type, edge.to_id)
               not in config.manifest_scope.edge_tuples for edge in graph.edges):
            raise WriterAdapterError('writer refused edge outside the exact sample manifest')
        for node in graph.nodes:
            _validate_node({'type': node.label, 'id': node.id, 'name': node.name,
                            'properties': node.properties}, config)
        for edge in graph.edges:
            fields = (edge.from_type, edge.from_id, edge.label, edge.to_type, edge.to_id)
            _validate_edge({'tuple': fields, 'application_edge_key': edge.id,
                            'properties': edge.properties}, config)
        return
    _validate_prefix(config.synthetic_prefix)
    for node in graph.nodes:
        if (not isinstance(node.id, str) or not node.id.startswith(config.synthetic_prefix)
                or any(char in node.id for char in '*?[]%')):
            raise WriterAdapterError('writer refused node outside the synthetic prefix')
        spec = {'type': node.label, 'id': node.id, 'name': node.name,
                'properties': node.properties}
        if deleting:
            _validate_node_identity(spec, config)
        else:
            _validate_node(spec, config)
    for edge in graph.edges:
        if any(not isinstance(identity, str) or not identity.startswith(config.synthetic_prefix)
               or any(char in identity for char in '*?[]%')
               for identity in (edge.from_id, edge.to_id)):
            raise WriterAdapterError('writer refused edge outside the synthetic prefix')
        edge_tuple = (edge.from_type, edge.from_id, edge.label, edge.to_type, edge.to_id)
        if edge.id != application_edge_key(edge_tuple):
            raise WriterAdapterError('writer refused edge without its exact C2 application key')
        spec = {'tuple': edge_tuple, 'application_edge_key': edge.id,
                'properties': edge.properties}
        _validate_edge(spec, config)


def _plan_specs(plan_or_specs: Any) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]]]:
    if isinstance(plan_or_specs, Mapping):
        nodes, edges = plan_or_specs.get('nodes'), plan_or_specs.get('edges')
    else:
        nodes, edges = getattr(plan_or_specs, 'nodes', None), getattr(plan_or_specs, 'edges', None)
    if not isinstance(nodes, Sequence) or not isinstance(edges, Sequence):
        raise WriterAdapterError('plan must expose ordered nodes and edges sequences')
    return list(nodes), list(edges)


def _check_writer_config(writer: Any, config: WriterConfig) -> None:
    other = getattr(writer, 'config', None)
    fields = ('host_addr', 'project_id', 'project_name', 'namespace', 'synthetic_prefix',
              'scope', 'manifest_scope', 'production_scope')
    if (not isinstance(other, WriterConfig)
            or any(getattr(other, field) != getattr(config, field) for field in fields)
            or other.contract != config.contract):
        raise WriterAdapterError('writer target differs from the verified smoke-project configuration')


def _check_client_target(client: Any, config: WriterConfig, role: str) -> None:
    if client is None:
        raise WriterAdapterError(f'{role} client is missing')
    configured = isinstance(getattr(client, 'config', None), WriterConfig)
    if configured:
        _check_writer_config(client, config)
    actual_host = getattr(client, '_host_addr', None)
    actual_project = getattr(client, '_project_id', None)
    if actual_host is not None and actual_host != config.host_addr:
        raise WriterAdapterError(f'{role} client is bound to a different OpenSPG host')
    if actual_project is not None and str(actual_project) != str(config.project_id):
        raise WriterAdapterError(f'{role} client is bound to a different OpenSPG project')
    if not configured and (actual_host != config.host_addr
                           or str(actual_project) != str(config.project_id)):
        raise WriterAdapterError(f'{role} client is not bound to the verified smoke project')


def _assert_synthetic_scope(nodes: Sequence[Mapping[str, Any]], edges: Sequence[Mapping[str, Any]],
                            prefix: str) -> None:
    _validate_prefix(prefix)
    identities = set()
    for node in nodes:
        identity = node.get('id')
        if not isinstance(identity, str) or not identity.startswith(prefix) or any(c in identity for c in '*?[]%'):
            raise WriterAdapterError('staged C4.1 writes require exact IDs under the synthetic prefix')
        key = (node.get('type'), identity)
        if key in identities:
            raise WriterAdapterError('staged C4.1 writes reject duplicate node identities')
        identities.add(key)
    if edges and not nodes:
        raise WriterAdapterError('edge stage requires nodes to pass the readback barrier first')
    for edge in edges:
        fields = tuple(edge.get('tuple', ()))
        if len(fields) != 5 or (fields[0], fields[1]) not in identities or (fields[3], fields[4]) not in identities:
            raise WriterAdapterError('staged edge endpoints must be exact nodes in the synthetic plan')


class OpenSPGReadClient:
    """Expose exact identity metadata from pinned ReasonerClient's type query."""

    def __init__(self, config: WriterConfig, reasoner_client: Any):
        if not isinstance(config, WriterConfig):
            raise WriterAdapterError('an explicit WriterConfig is required for OpenSPG readback')
        self.config = config
        self._reasoner_client = reasoner_client
        _check_client_target(reasoner_client, config, 'ReasonerClient')
        if not callable(getattr(getattr(reasoner_client, '_rest_client', None),
                                'query_spg_type_post', None)):
            raise WriterAdapterError('ReasonerClient does not expose pinned query_spg_type_post')

    def query_node(self, node_type: str, node_id: str) -> dict[str, Any] | None:
        """Query one exact ID and retain type/id omitted by ReasonerClient.query_node."""
        from knext.reasoner.rest import SpgTypeQueryRequest

        request = SpgTypeQueryRequest(project_id=str(self.config.project_id),
                                       spg_type=node_type, ids=[node_id])
        rows = self._reasoner_client._rest_client.query_spg_type_post(
            spg_type_query_request=request)
        if not rows:
            return None
        row = rows[0]
        return {'type': getattr(row, 'spg_type', None),
                'id': getattr(row, 'id', None),
                'properties': getattr(row, 'properties', None)}


def verify_nodes(expected_nodes: Sequence[Mapping[str, Any]], read_client: Any,
                 contract: WriterConfig) -> dict[str, Any]:
    """Read every expected node and compare identity, name, and decoded properties."""
    if not isinstance(contract, WriterConfig):
        raise NodeReadbackError('readback requires the verified smoke-project WriterConfig')
    config = contract
    if read_client is None or not callable(getattr(read_client, 'query_node', None)):
        raise NodeReadbackError('read_client must provide query_node(type, id)')
    _check_client_target(read_client, config, 'readback')
    verified = []
    for spec in expected_nodes:
        type_name, identity, name, props = _validate_node(spec, config)
        try:
            response = read_client.query_node(type_name, identity)
        except Exception as exc:
            raise NodeReadbackError(f'{type_name}/{identity}: readback request failed: {exc}') from exc
        if response is None or response == {}:
            raise NodeReadbackError(f'{type_name}/{identity}: node not found')
        if isinstance(response, Mapping):
            actual_type = response.get('type', response.get('spg_type'))
            actual_id = response.get('id')
            actual_props = response.get('properties', response)
        else:
            actual_type = getattr(response, 'spg_type', None)
            actual_id = getattr(response, 'id', None)
            actual_props = getattr(response, 'properties', None)
        if not isinstance(actual_props, Mapping):
            raise NodeReadbackError(f'{type_name}/{identity}: response has no property mapping')
        if actual_type != type_name:
            raise NodeReadbackError(f'{type_name}/{identity}: readback type mismatch {actual_type!r}')
        if actual_id != identity:
            raise NodeReadbackError(f'{type_name}/{identity}: readback id mismatch {actual_id!r}')
        physical = dict(actual_props)
        if 'id' in physical and physical['id'] != identity:
            raise NodeReadbackError(f'{type_name}/{identity}: physical id mismatch')
        physical.setdefault('id', actual_id)  # exact response metadata was checked above
        if physical.get('name') != name:
            # Reasoner wraps name in JSON Text while id metadata remains plain.
            # Decode exactly one string envelope; never coerce numeric identities.
            try:
                decoded_name = json.loads(physical.get('name'))
            except (TypeError, ValueError):
                decoded_name = None
            if not isinstance(decoded_name, str) or decoded_name != name:
                raise NodeReadbackError(f'{type_name}/{identity}: readback name mismatch')
            physical['name'] = decoded_name
        rows = config.contract['node_properties'][type_name.rsplit('.', 1)[-1]]
        try:
            actual = decode_properties(physical, rows, server_encoded=True)
            expected_physical = dict(props, id=identity, name=name)
            expected = decode_properties(expected_physical, rows, server_encoded=False)
        except BuilderContractError as exc:
            raise NodeReadbackError(f'{type_name}/{identity}: invalid readback properties: {exc}') from exc
        if canonical_json(actual) != canonical_json(expected):
            raise NodeReadbackError(f'{type_name}/{identity}: decoded property mismatch')
        verified.append({'type': type_name, 'id': identity, 'name': name})
    return {'verified': len(verified), 'nodes': verified}


def write_nodes_then_edges(plan_or_specs: Any, config: WriterConfig, read_client: Any, *,
                           writer: Any = None, batch_size: int = 1000) -> dict[str, Any]:
    """Write all node batches, prove full node readback, then write edge-only batches."""
    if not isinstance(config, WriterConfig):
        raise WriterAdapterError('an explicit WriterConfig is required')
    config.__post_init__()
    nodes, edges = _plan_specs(plan_or_specs)
    if config.scope == 'C4_1_SMOKE':
        _assert_synthetic_scope(nodes, edges, config.synthetic_prefix)
    elif config.scope == 'PRODUCTION':
        config.production_scope.validate_specs(nodes, edges, require_vectors=True, complete=True)
    else:
        config.manifest_scope.verify_file()
        keys = [(node['type'], node['id']) for node in nodes]
        tuples = [tuple(edge['tuple']) for edge in edges]
        if (len(keys) != len(config.manifest_scope.node_keys) or set(keys) != config.manifest_scope.node_keys
                or len(tuples) != len(config.manifest_scope.edge_tuples)
                or set(tuples) != config.manifest_scope.edge_tuples):
            raise WriterAdapterError('staged C4.3a plan must equal the entire manifest')
    node_batches = to_subgraphs(nodes, batch_size, 'nodes', config)
    edge_batches = to_subgraphs(edges, batch_size, 'edges', config)
    if read_client is None:
        raise NodeReadbackError('readback barrier is required before any edge write')
    active_writer = writer if writer is not None else NativeIntegerKGWriter(config)
    _check_writer_config(active_writer, config)
    _check_client_target(getattr(active_writer, 'client', None), config, 'writer')
    _check_client_target(read_client, config, 'readback')
    for batch in node_batches:
        active_writer.write_subgraph(batch, 'nodes')
    readback = verify_nodes(nodes, read_client, config)
    if isinstance(active_writer, NativeIntegerKGWriter):
        active_writer._mark_nodes_verified(readback['nodes'])
    for batch in edge_batches:
        active_writer.write_subgraph(batch, 'edges')
    return {'nodes_planned': len(nodes), 'nodes_written': len(nodes),
            'nodes_verified': readback['verified'], 'edges_planned': len(edges),
            'edges_written': len(edges), 'node_readback': readback}


def cleanup_synthetic(writer: Any, node_specs: Sequence[Mapping[str, Any]],
                      edge_specs: Sequence[Mapping[str, Any]], prefix: str,
                      contract: WriterConfig, batch_size: int = 1000) -> dict[str, int]:
    """Delete only exact prefix-scoped synthetic edges, then their exact endpoint nodes."""
    if not isinstance(contract, WriterConfig):
        raise WriterAdapterError('cleanup requires the verified smoke-project WriterConfig')
    config = contract
    if config.scope != 'C4_1_SMOKE':
        raise WriterAdapterError('synthetic cleanup cannot use a C4.3a manifest scope')
    _validate_prefix(prefix)
    if config.synthetic_prefix != prefix:
        raise WriterAdapterError('cleanup prefix differs from the configured synthetic prefix')
    _check_writer_config(writer, config)
    _check_client_target(getattr(writer, 'client', None), config, 'cleanup writer')
    exact_nodes: dict[tuple[str, str], Node] = {}
    for spec in node_specs:
        type_name, identity, name, _ = _validate_node_identity(spec, config)
        if not identity.startswith(prefix) or any(char in identity for char in '*?[]%'):
            raise WriterAdapterError('cleanup refused node outside the exact synthetic prefix')
        key = (type_name, identity)
        if key in exact_nodes:
            raise WriterAdapterError('cleanup refused duplicate synthetic node identity')
        exact_nodes[key] = Node(_id=identity, name=name, label=type_name, properties={})
    exact_edges = []
    for spec in edge_specs:
        edge_tuple, edge_key, _ = _validate_edge(spec, config)
        from_type, from_id, predicate, to_type, to_id = edge_tuple
        if ((from_type, from_id) not in exact_nodes or (to_type, to_id) not in exact_nodes
                or not from_id.startswith(prefix) or not to_id.startswith(prefix)):
            raise WriterAdapterError('cleanup refused edge with endpoint outside exact synthetic IDs')
        from_node = Node(_id=from_id, name=from_id, label=from_type, properties={})
        to_node = Node(_id=to_id, name=to_id, label=to_type, properties={})
        exact_edges.append(Edge(_id=edge_key, from_node=from_node, to_node=to_node,
                                label=predicate, properties={}))
    if type(batch_size) is not int or batch_size < 1:
        raise WriterAdapterError('batch_size must be a positive native int')
    for offset in range(0, len(exact_edges), batch_size):
        writer.delete_subgraph(SubGraph([], exact_edges[offset:offset + batch_size]), 'edges')
    node_values = list(exact_nodes.values())
    for offset in range(0, len(node_values), batch_size):
        writer.delete_subgraph(SubGraph(node_values[offset:offset + batch_size], []), 'nodes')
    return {'edges_deleted': len(exact_edges), 'nodes_deleted': len(node_values)}


def _validate_node_identity(spec: Mapping[str, Any], config: WriterConfig | _ContractContext) -> tuple[str, str, str, dict[str, Any]]:
    try:
        type_name, identity, name = spec['type'], spec['id'], spec['name']
        _local_type_name(type_name, config.namespace, config.contract['node_types'])
        if not isinstance(identity, str) or not identity.strip() or name != identity:
            raise WriterAdapterError('node id/name must be the same nonblank exact Text')
        return type_name, identity, name, {}
    except (KeyError, TypeError) as exc:
        raise WriterAdapterError(f'invalid cleanup node identity: {exc}') from exc

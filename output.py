"""Public decision views; internal recognition/click records remain complete."""

import copy

SCORE_FIELDS = frozenset({'score', 'ocr_score', 'ncc', 'signed_ncc'})


def compact_scores(value):
    """Return a JSON-ready copy with score/NCC numbers at 3 significant digits."""
    if isinstance(value, dict):
        return {
            key: (float(format(item, '.3g'))
                  if key in SCORE_FIELDS and isinstance(item, (int, float))
                  and not isinstance(item, bool) else compact_scores(item))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [compact_scores(item) for item in value]
    return value


def output_format(request):
    value = request.get('format', 'agent')
    if value not in ('agent', 'full'):
        raise ValueError('format_must_be_agent_or_full')
    return value


def decision_state(value):
    """Remove diagnostic provenance, never coerce unknown/false/zero values."""
    if isinstance(value, (list, tuple)):
        return [decision_state(item) for item in value]
    if not isinstance(value, dict):
        return value
    omitted = {'schema', 'source', 'evidence', 'bounds', 'cost_profile',
               'full_tolerance_pixels', 'exact_hp', 'visible_panel_text',
               'blue_markers', 'presets'}
    return {key: decision_state(item) for key, item in value.items()
            if key not in omitted and not key.endswith(('_evidence', '_bounds'))}


def _walk(node, parents=()):
    yield node, parents
    for child in node.get('children', []):
        yield from _walk(child, parents + (node,))


def decision_node(node, parents=()):
    # Preserve the row's meaning when many cards all have "进入"/"追踪" buttons.
    context = [p.get('name', '') for p in parents
               if p.get('key', '').startswith(('content/', 'task/'))]
    name = ' / '.join([*context, node.get('name', '')])
    result = {key: node[key] for key in ('ref',) if key in node}
    result.update(name=name, effect=node.get('effect'))
    if node.get('actions') and node['actions']!=['click']:
        result['actions']=node['actions']
    # enabled absent/null means unknown, never implicitly enabled. All semantic
    # flags (including null selected/checked) remain exact when they were present.
    for key in ('enabled', 'selected', 'checked', 'notification', 'target_kind',
                'semantic_status', 'value', 'minimum', 'maximum'):
        if key in node and (key != 'enabled' or node[key] is not None):
            result[key] = copy.deepcopy(node[key])
    return result


def decision_observation(observation, detail='navigation'):
    result = {'schema': 'hsr-agent-v1', 'page': observation.get('page', 'unknown'),
              'coverage': 'partial',
              'observationId': observation.get('observationId'),
              'live': observation.get('live', False)}
    if observation.get('expires_in_seconds') is not None:
        result['expires_in_seconds'] = observation['expires_in_seconds']
    result['nodes'] = []
    text = []
    for node, parents in _walk(observation.get('tree', {})):
        if node.get('actions'):
            result['nodes'].append(decision_node(node, parents))
        elif not node.get('children') and node.get('name') and (
                detail == 'content' or node.get('key', '').startswith('title/')):
            if node['name'] not in text:
                text.append(node['name'])
    if text:
        result['text'] = text
    if 'state' in observation:
        result['state'] = decision_state(observation['state'])
    if result['page'] == 'unknown':
        # A malformed unknown tree must never expose inferred actions.
        result['nodes'] = []
        result['reason'] = observation.get('reason', 'unknown_or_transition')
    return result


def agent_response(response, request):
    """Project only at the CLI/plugin boundary, never mutate worker/web data."""
    if output_format(request) == 'full':
        return compact_scores(response)
    if not response.get('ok'):
        return compact_scores(response)
    original = response.get('result', {})
    if 'tree' in original:
        result = decision_observation(original, request.get('detail', 'navigation'))
    elif request.get('action') in ('click','scroll'):
        result = {key: copy.deepcopy(original[key]) for key in
                  ('tapped', 'scrolled', 'validated', 'name', 'effect', 'settled', 'transition_observed')
                  if key in original}
        if request.get('dryRun'):
            result['dryRun'] = True
        if 'node' in original:
            # Internal validation captures have fresh, non-current refs. Do not
            # advertise those refs as reusable after a dry-run.
            target = decision_node(original['node'])
            target.pop('ref', None)
            result['node'] = target
        if 'observation' in original:
            result['observation'] = (decision_observation(original['observation'],
                                      request.get('detail', 'navigation'))
                                      if original['observation'] is not None else None)
    else:
        result = {key: copy.deepcopy(original[key]) for key in
                  ('ready', 'device', 'video_active', 'released') if key in original}
    return compact_scores({'ok': True, 'result': result})

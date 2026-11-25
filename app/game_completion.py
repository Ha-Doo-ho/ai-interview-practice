"""Result access policy; gameplay and saved source evidence remain separate."""
from .store import Conflict

def all_games_complete(snapshot):
    if snapshot.get('flow_version') != 'five-game-v2':
        return True
    rules=snapshot.get('rule_games',{}).get('games',{})
    if any(len(rules.get(k,{}).get('rounds',[]))!=3 or
           any(r.get('status')!='completed' for r in rules[k]['rounds']) for k in ('rsp','card')):
        return False
    appointments=snapshot.get('appointment_games',{}).get('games',[])
    if ([g.get('type') for g in appointments]!=['day','place','bus'] or
        any(g.get('status')!='complete' or len(g.get('questions',[]))!=10 for g in appointments)):
        return False
    attempts=snapshot.get('aptitude_games',{}).get('attempts',[])
    return (not any(a.get('status')=='active' for a in attempts) and
            all(any(a.get('type')==kind and a.get('mode')=='main' and a.get('status')=='complete'
                    for a in attempts) for kind in ('rotation','path','potion')))

def require_all_games(snapshot):
    if not all_games_complete(snapshot):
        raise Conflict('all_games_completion_required')

def results_visible(snapshot):
    return snapshot.get('status')=='completed' or all_games_complete(snapshot)

def hide_partial_results(public, *, visibility_snapshot=None):
    """Filter a response copy only; never erase stored reports or source history."""
    if results_visible(public if visibility_snapshot is None else visibility_snapshot):
        return
    for field in ('analysis','report','report_draft','interview_report','interview_analysis',
                  'game_analysis','synthesis_analysis','evidence_linkage'):
        public.pop(field,None)
        public.pop(field+'_history',None)
    conditioned={q['question_id'] for q in public.get('questions',[])
                 if q.get('conditioned_on_prior_evidence') or q.get('question_mode')=='adaptive_followup'}
    public['questions']=[q for q in public.get('questions',[]) if q['question_id'] not in conditioned]
    public['records']=[r for r in public.get('records',[]) if r.get('data',{}).get('question_id') not in conditioned
        and not r.get('data',{}).get('conditioned_on_prior_evidence')
        and r.get('data',{}).get('question_mode')!='adaptive_followup']
    for attempt in public.get('aptitude_games',{}).get('attempts',[]):
        attempt.pop('summary',None)

/* Account-owned server run inventory. No local storage records or inferred scores. */
(function(){
  'use strict';
  const $=id=>document.getElementById(id);
  let context=null;
  const element=(tag,text)=>{const node=document.createElement(tag);if(text!==undefined)node.textContent=String(text);return node;};
  const locked=()=>!context?.user||!context.ready||context.busy||context.locked||context.gameLocked||context.interviewLocked||context.reportLocked;
  function render(next){
    if(next)context=next;
    if(!$('recordsTbody'))return;
    const root=$('recordsTbody');root.replaceChildren();
    const runs=context?.user?(context.runs||[]).filter(run=>run.user_id===context.user.user_id):[];
    $('records-status').textContent=!context?.user?'로그인한 계정의 서버 기록을 확인할 수 있습니다.':context.busy?'서버 기록을 확인하는 중입니다.':!context.ready?'서버 기록을 불러오지 못했습니다. 다시 불러오기를 눌러 주세요.':`내 서버 기록 ${runs.length}개 · 현재 계정의 회차만 표시합니다.`;
    if($('records-error')){$('records-error').textContent=context?.error||'';$('records-error').hidden=!context?.error;}
    $('records-refresh').disabled=!context?.user||context.busy||context.locked||context.gameLocked||context.interviewLocked||context.reportLocked;
    $('noDataAlert').style.display=runs.length?'none':'block';
    $('noDataAlert').textContent=!context?.user?'로그인 후 저장된 회차를 확인해 주세요.':context.ready?'저장된 서버 기록이 없습니다.':'서버 기록을 불러오는 중이거나 확인이 필요합니다.';
    runs.forEach((run,index)=>{
      const row=element('tr');
      for(const text of [run.created_at?new Date(run.created_at).toLocaleString('ko-KR'):'시각 없음',run.run_id,run.status==='completed'?'최종 확정':'연습 진행 중',`Rev. ${run.revision}`])row.append(element('td',text));
      const actions=element('td');
      const canOpen=()=>!locked() || window.AstraPractice.canResumeCurrentGame?.(run.run_id);
      const open=element('button',run.status==='completed'?'최종 보고서 보기':'이어하기');open.type='button';open.className='btn-action btn-light btn-sm';open.setAttribute('id',`records-open-${index}`);open.disabled=!canOpen();
      open.addEventListener('click',()=>{if(canOpen())return window.AstraPractice.openRun(run.run_id);});
      const remove=element('button','삭제');remove.type='button';remove.className='btn-action btn-light btn-sm';remove.setAttribute('id',`records-delete-${index}`);remove.disabled=locked();
      remove.addEventListener('click',()=>{if(locked())return;if(!window.confirm('이 회차의 설문·게임·면접 원본과 파생 보고서를 서버에서 삭제하시겠습니까? 삭제한 회차는 복구할 수 없습니다.'))return;return window.AstraPractice.deleteRun(run.run_id);});
      actions.append(open,remove);row.append(actions);root.append(row);
    });
  }
  window.AstraRecords={render};
  document.addEventListener('DOMContentLoaded',()=>{
    if(!['subscribe','refreshRuns','openRun','deleteRun'].every(name=>typeof window.AstraPractice?.[name]==='function')){$('records-status').textContent='기록 화면 파일을 불러오지 못했습니다. Ctrl + F5로 새로고침해 주세요.';$('records-refresh').disabled=true;return;}
    $('records-refresh').addEventListener('click',()=>{if(!context?.busy)return window.AstraPractice.refreshRuns();});
    window.AstraPractice.subscribe(render);
  });
})();

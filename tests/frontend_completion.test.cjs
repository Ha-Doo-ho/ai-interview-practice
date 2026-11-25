const {test}=require('node:test');
const assert=require('node:assert/strict');
const C=require('../html/client.js');
function complete(){return {flow_version:'five-game-v2',rule_games:{games:Object.fromEntries(['rsp','card'].map(k=>[k,{rounds:Array.from({length:3},()=>({status:'completed'}))}]))},appointment_games:{games:['day','place','bus'].map(type=>({type,status:'complete',questions:Array(10).fill({})}))},aptitude_games:{attempts:['rotation','path','potion'].map(type=>({type,mode:'main',status:'complete'}))}};}
test('all eight different main games must be complete before results',()=>{
  assert.equal(C.allGamesComplete(complete()),true);
  for(const [mode,status] of [['practice','complete'],['quick','complete'],['main','interrupted'],['main','active']]){
    const run=complete();run.aptitude_games.attempts[2]={type:'potion',mode,status};
    run.aptitude_games.attempts.push({type:'rotation',mode:'main',status:'complete'});
    assert.equal(C.allGamesComplete(run),false);
  }
  const run=complete();run.aptitude_games.attempts.push({type:'rotation',mode:'main',status:'interrupted'});
  assert.equal(C.allGamesComplete(run),true);
});
test('missing appointment and an active replay keep current results locked',()=>{
  const run=complete();run.appointment_games.games[1].status='pending';assert.equal(C.allGamesComplete(run),false);
  run.appointment_games.games[1].status='complete';run.aptitude_games.attempts.push({type:'path',mode:'practice',status:'active'});
  assert.equal(C.allGamesComplete(run),false);
  assert.equal(C.allGamesComplete({}),true);
});

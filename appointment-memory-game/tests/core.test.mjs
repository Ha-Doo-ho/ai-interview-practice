import test from 'node:test';
import assert from 'node:assert/strict';
import { RULES, makeQuestion, applyScore, phaseAt } from '../dist/core.mjs';
function rng(seed) { return () => { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296; }; }
test('weekday easy shows A, B and C for three seconds each', () => {
 assert.deepEqual(RULES.day?.easy, { count:3, reveal:[3000,3000,3000], answer:6000 });
 assert.deepEqual(RULES.day?.hard, { count:4, reveal:[1500,1500,1500], answer:3000 });
});
test('place and bus timings match their difficulty',()=>{
 assert.deepEqual(RULES.place?.easy,{count:3,reveal:[3000,3000,3000],answer:5000});
 assert.deepEqual(RULES.place?.hard,{count:4,reveal:[1500,1500,1500],answer:3000});
 assert.deepEqual(RULES.bus?.easy,{count:2,reveal:[3000,3000,3000],answer:5000});
 assert.deepEqual(RULES.bus?.hard,{count:2,reveal:[1500,1500,1500],answer:3000});
});
for (const game of ['day','place']) for(const difficulty of ['easy','hard']) {
 test(`${game}/${difficulty}: 1000 random problems have exactly one common answer`,()=>{
  const random=rng(92); for(let i=0;i<1000;i++){
   const q=makeQuestion(game,difficulty,random); assert.ok(q,'question generated');
   assert.equal(q.sets.length,3);
   for(const set of q.sets){assert.equal(set.length,difficulty==='easy'?3:4);assert.equal(new Set(set).size,set.length);}
   const common=q.sets[0].filter(v=>q.sets[1].includes(v)&&q.sets[2].includes(v));
   assert.deepEqual(common,[q.answer]);assert.ok(q.choices.includes(q.answer));assert.equal(new Set(q.choices).size,q.choices.length);
   assert.equal(q.choices.length,game==='day'?7:16);
  }
 });
}
test('bus: two per person and exactly one of six options is unused',()=>{
 const random=rng(180);for(let i=0;i<1000;i++){
  const q=makeQuestion('bus','easy',random);assert.ok(q,'question generated');
  assert.equal(q.sets.length,3);for(const set of q.sets){assert.equal(set.length,2);assert.equal(new Set(set).size,2);}
  assert.equal(q.choices.length,6);assert.equal(new Set(q.choices).size,6);
  assert.deepEqual(q.choices.filter(v=>!q.sets.flat().includes(v)),[q.answer]);
 }
});
test('score gains ten, loses five and never falls below zero',()=>{
 assert.equal(applyScore(0,'correct'),10);assert.equal(applyScore(10,'wrong'),5);assert.equal(applyScore(0,'wrong'),0);assert.equal(applyScore(3,'timeout'),0);assert.equal(applyScore(15,'timeout'),10);
});
test('phases switch at exact boundaries and timeout at the deadline',()=>{
 const rule={reveal:[3000,1000,1000],answer:6000};
 assert.deepEqual(phaseAt(0,rule),{phase:'reveal',person:0,remaining:3000,duration:3000});
 assert.equal(phaseAt(2999,rule)?.person,0);assert.equal(phaseAt(3000,rule)?.person,1);
 assert.equal(phaseAt(4000,rule)?.person,2);assert.equal(phaseAt(5000,rule)?.phase,'answer');
 assert.equal(phaseAt(10999,rule)?.remaining,1);assert.equal(phaseAt(11000,rule)?.phase,'timeout');assert.equal(phaseAt(90000,rule)?.phase,'timeout');
});

test('weekday easy gives B and C their full three seconds before the six-second answer window',()=>{
 const r=RULES.day.easy;
 assert.equal(phaseAt(5999,r).person,1);
 assert.equal(phaseAt(6000,r).person,2);
 assert.equal(phaseAt(8999,r).person,2);
 assert.equal(phaseAt(9000,r).phase,'answer');
 assert.equal(phaseAt(9000,r).remaining,6000);
 assert.equal(phaseAt(15000,r).phase,'timeout');
});

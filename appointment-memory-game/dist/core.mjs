export const RULES = {
 day: { easy:{count:3,reveal:[3000,3000,3000],answer:6000}, hard:{count:4,reveal:[1500,1500,1500],answer:3000} },
 place: { easy:{count:3,reveal:[3000,3000,3000],answer:5000}, hard:{count:4,reveal:[1500,1500,1500],answer:3000} },
 bus: { easy:{count:2,reveal:[3000,3000,3000],answer:5000}, hard:{count:2,reveal:[1500,1500,1500],answer:3000} }
};
export function shuffle(values, random=Math.random) {
 const result=[...values];for(let i=result.length-1;i>0;i--){const j=Math.floor(random()*(i+1));[result[i],result[j]]=[result[j],result[i]];}return result;
}
export function makeQuestion(game,difficulty,random=Math.random) {
 const rule=RULES[game][difficulty];
 if(game==='bus'){
  const numbers=shuffle(Array.from({length:899},(_,i)=>i+1),random).slice(0,6);
  // Five distinct used numbers over six mentions; the sixth option is never used.
  const sets=shuffle([[numbers[0],numbers[1]],[numbers[2],numbers[3]],[numbers[4],numbers[Math.floor(random()*4)]]],random).map(s=>shuffle(s,random));
  return {sets,answer:numbers[5],choices:shuffle(numbers,random)};
 }
 const choices=Array.from({length:game==='day'?7:16},(_,i)=>i);
 const pool=shuffle(choices,random), answer=pool.pop();
 // The distractor patterns overlap pairwise, but never across all three people.
 const pattern=rule.count===3?[[0,1],[1,2],[2,3]]:[[0,1,2],[2,3,4],[0,4,5]];
 const sets=shuffle(pattern,random).map(p=>shuffle([answer,...p.map(i=>pool[i])],random));
 return {sets,answer,choices};
}
export function applyScore(score,outcome) {return Math.max(0,score+(outcome==='correct'?10:-5));}
export function phaseAt(elapsed,rule) {
 let boundary=0;
 for(let person=0;person<3;person++){const duration=rule.reveal[person];boundary+=duration;if(elapsed<boundary)return {phase:'reveal',person,remaining:boundary-elapsed,duration};}
 boundary+=rule.answer;
 return elapsed<boundary?{phase:'answer',remaining:boundary-elapsed,duration:rule.answer}:{phase:'timeout',remaining:0,duration:rule.answer};
}

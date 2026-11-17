const trees=(points)=>points.map(([x,y],i)=>`<circle cx="${x}" cy="${y}" r="4.2" fill="${i%2?'#76ad57':'#92bf70'}"/><circle cx="${x-1}" cy="${y-1}" r="2" fill="#b2ce8d" opacity=".65"/>`).join('');
const box=(x,y,w,h,c)=>`<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="1" fill="${c}"/>`;
const red=(x,y,w,h)=>box(x,y,w,h,'#f57c52')+box(x,y+h*.53,w,h*.47,'#e75a32');
const gray=(x,y,w,h)=>box(x,y,w,h,'#a4b3b6')+box(x+4,y+5,w-8,h*.3,'#d8e4e5');
const pool=(x,y)=>box(x,y,25,26,'#f3f4df')+`<ellipse cx="${x+12.5}" cy="${y+13}" rx="10" ry="11" fill="#86c6dc"/><circle cx="${x+17}" cy="${y+8}" r="2.5" fill="#d7eff1"/>`;
const windows=(x,y,cols,rows)=>Array.from({length:cols*rows},(_,i)=>box(x+(i%cols)*14,y+Math.floor(i/cols)*15,10,10,'#f6f6e8')).join('');
const art=[
 red(12,5,20,49)+red(32,15,15,20)+pool(51,17)+trees([[7,10],[7,27],[7,45]]),
 red(24,13,26,40)+red(54,5,32,48)+trees([[12,13],[17,24],[12,35]]),
 box(31,6,52,49,'#cfbda6')+box(36,11,42,39,'#a7b7bd')+windows(40,14,2,2)+trees([[12,12],[12,29],[12,46]]),
 red(30,12,46,39)+box(40,50,27,7,'#cfa68f')+trees([[10,10],[11,21],[14,32],[55,58]]),
 gray(16,13,55,38)+box(25,45,7,6,'#7f9196')+box(57,45,7,6,'#7f9196')+trees([[7,15],[7,32],[7,48],[80,51]])+box(81,9,3,8,'#d1b786'),
 gray(10,10,30,42)+windows(15,16,2,1)+red(44,10,39,42)+trees([[18,58],[32,58]]),
 red(12,7,19,48)+red(31,42,28,13)+pool(35,11)+trees([[75,12],[75,29],[75,45],[58,56]]),
 red(12,11,20,44)+red(35,11,47,44)+box(46,20,11,11,'#f6ede1')+trees([[47,60],[65,60],[82,60]]),
 gray(29,10,47,44)+box(36,16,32,12,'#e9f1e8')+box(56,42,10,12,'#85969c')+trees([[10,14],[18,25],[10,34],[14,48]]),
 red(10,10,55,44)+trees([[74,12],[84,12],[74,24],[84,24],[74,36],[84,36],[74,48],[84,48]]),
 red(11,6,73,32)+red(19,38,56,15)+box(39,52,22,8,'#d5a289')+trees([[11,59],[82,59]]),
 red(32,10,48,44)+box(10,10,6,6,'#bdcdd0')+trees([[15,44],[22,53],[12,58]]),
 red(10,8,20,48)+red(30,42,43,14)+red(49,14,18,17)+trees([[83,12],[83,26],[83,41],[83,55]]),
 red(27,20,42,34)+trees([[10,16],[10,31],[10,46],[27,7],[40,7],[53,7],[82,28],[82,44]]),
 gray(20,8,61,47)+windows(26,14,3,2)+trees([[10,11],[10,28],[10,46],[49,60]]),
 red(13,15,64,37)+box(21,23,48,19,'#b4cacf')+windows(24,26,3,1)+trees([[86,28],[86,44],[86,57]])
];
export function placeArt(i){return `<svg viewBox="0 0 96 66" aria-hidden="true"><rect width="96" height="66" rx="4" fill="#e3e7e1"/>${art[i]}</svg>`;}
export function townHTML({highlight=[],interactive=false,answer=null,selected=null}={}){
 return `<div class="town" aria-label="16개 장소 지도"><svg class="road" viewBox="0 0 520 350" aria-hidden="true"><rect width="520" height="350" fill="#585e66"/><path d="M260 0V350 M0 175H520" stroke="#81878b" stroke-width="2" stroke-dasharray="9 15"/><g fill="#eceee9"><rect x="0" y="0" width="234" height="156" rx="12"/><rect x="286" y="0" width="234" height="156" rx="12"/><rect x="0" y="194" width="234" height="156" rx="12"/><rect x="286" y="194" width="234" height="156" rx="12"/></g></svg>${Array.from({length:16},(_,i)=>{const col=i%4,row=Math.floor(i/4),x=[7,120,293,406][col],y=[6,81,200,275][row];const tag=interactive?'button':'div';return `<${tag} ${interactive?`type="button" data-answer="${i}" aria-label="장소 ${i+1}"`:''} class="place-tile ${interactive?'answer':highlight.includes(i)?'highlight':'dim'} ${answer===i?'correct':''} ${selected===i&&answer!==i?'wrong':''}" style="left:${x/520*100}%;top:${y/350*100}%;width:${107/520*100}%;height:${69/350*100}%">${placeArt(i)}${interactive?`<span class="tile-number">${i+1}</span>`:''}</${tag}>`;}).join('')}</div>`;
}

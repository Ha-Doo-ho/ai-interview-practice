// Exercise the actual old renderer's version boundary without mounting user data.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

test('historical static UI sends versioned questionnaires to the canonical screen',()=>{
  const source=fs.readFileSync('app/static/app.js','utf8');
  const render=source.slice(source.indexOf('  function renderRun()'),source.indexOf('  function optionsFor('));
  let shown;
  const context={state:{run:{survey_set_version:'work-behavior-v2'}},clearError(){},
    h:(tag,attrs,children)=>({tag,attrs,children}),replace:node=>{shown=node;},
    runStage(){throw Error('old survey must not render a versioned run');}};
  vm.runInNewContext(render+'; renderRun();',context);
  assert.match(JSON.stringify(shown),/#survey/);
  assert.match(JSON.stringify(shown),/새 화면/);
  let legacyRendered=false;
  context.state.run={};context.runStage=()=> 'survey';context.renderSurvey=()=>{legacyRendered=true;};
  vm.runInNewContext(render+'; renderRun();',context);
  assert.equal(legacyRendered,true);
});

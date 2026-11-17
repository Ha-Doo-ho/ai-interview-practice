async (page) => {
  const check = (condition, message) => { if (!condition) throw new Error(message); };
  await page.getByRole('button', { name: '라운드 시작', exact: true }).click();
  await page.getByLabel('초기 자원 배분', { exact: true }).waitFor();
  let release;
  let reached;
  const intercepted = new Promise(resolve => { reached = resolve; });
  const handler = async route => {
    if (route.request().method() === 'POST' && route.request().postDataJSON().action === 'open_info') {
      reached();
      await new Promise(resolve => { release = resolve; });
    }
    await route.continue();
  };
  await page.route('**/api/runs/*/game', handler);
  await page.getByRole('button', { name: '팀원 과제 정보 열기', exact: true }).click();
  await intercepted;
  const inputLocked = await page.getByLabel('초기 자원 배분', { exact: true }).isDisabled();
  const submitLocked = await page.getByRole('button', { name: '초기 배분 확정', exact: true }).isDisabled();
  const response = page.waitForResponse(r => r.url().endsWith('/game') && r.request().postDataJSON()?.action === 'open_info');
  release();
  await response;
  await page.unroute('**/api/runs/*/game', handler);
  check(inputLocked && submitLocked, 'Controls must remain disabled while information request is pending');
  await page.getByLabel('초기 자원 배분', { exact: true }).fill('4');
  await page.getByRole('button', { name: '초기 배분 확정', exact: true }).click();
  await page.getByRole('button', { name: '새 정보 확인', exact: true }).click();
  await page.getByLabel('최종 자원 배분', { exact: true }).fill('5');
  await page.getByRole('button', { name: '최종 선택 확정', exact: true }).click();
  await page.getByRole('button', { name: '다음 라운드', exact: true }).waitFor();
  const round = await page.evaluate(async () => {
    const run = await (await fetch('/api/runs/' + location.hash.split('/').pop())).json();
    return run.game.rounds[0];
  });
  check(round.initial_decision.personal === 4 && round.final_decision.personal === 5, 'User allocation must survive async information update');
  check(round.revision_outcome === 'changed_after_evidence', 'Changed choice must be preserved');
  return { status: 'passed', inputLocked, submitLocked, initialPersonal: round.initial_decision.personal,
    finalPersonal: round.final_decision.personal, revisionOutcome: round.revision_outcome,
    url: page.url() };
}

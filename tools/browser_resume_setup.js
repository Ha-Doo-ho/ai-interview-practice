async (page) => {
  await page.goto('http://127.0.0.1:8000/');
  await page.locator('h1').waitFor();
  if (await page.getByRole('button', { name: '처음 왔어요', exact: true }).count()) {
  await page.getByRole('button', { name: '처음 왔어요', exact: true }).click();
  await page.getByLabel('아이디', { exact: true }).fill('resume-' + Date.now());
  await page.getByLabel('비밀번호', { exact: true }).fill('synthetic-only-password');
  await page.getByRole('button', { name: '가입하고 시작', exact: true }).click();
  } else {
    await page.getByRole('button', { name: '기록', exact: true }).click();
  }
  await page.getByRole('button', { name: '새 연습 시작', exact: true }).click();
  for (let i = 0; i < 3; i++) {
    await page.locator('#selected_position-5').check();
    await page.getByRole('button', { name: '응답 저장', exact: true }).click();
    await page.getByText(`선택 ${i + 2} / 6`, { exact: true }).waitFor();
  }
  await page.locator('#self_position-4').check();
  await page.locator('#others_position-5').check();
  await page.getByRole('button', { name: '응답 저장', exact: true }).click();
  await page.getByRole('button', { name: '이 위치로 확정', exact: true }).click();
  for (let i = 0; i < 3; i++) await page.locator('.candidate-list button').first().click();
  await page.getByRole('button', { name: '3순위 항목을 위로', exact: true }).click();
  await page.getByRole('button', { name: '응답 저장', exact: true }).click();
  await page.getByRole('button', { name: '라운드 시작', exact: true }).waitFor();
  return { status: 'ready_for_game_regression', url: page.url() };
}

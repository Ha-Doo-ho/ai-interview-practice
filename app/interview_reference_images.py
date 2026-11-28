"""Optional, fixed visual references for two interview questions."""

from hashlib import sha256
from pathlib import Path

IMAGE_DIRECTORY = Path(__file__).resolve().parents[1] / 'reference_images'
MAX_IMAGE_BYTES = 512 * 1024
MIME_TYPE = 'image/png'
NCS_PROBLEM_SOLVING = 'https://m.ncs.go.kr/unity/th03/TH0309.do?jobCd=03'

REFERENCES = {
    'baseline-b03': {
        'filename': 'question-03-design-feedback.png',
        'sha256': '2172dacf097426063c08b355620d95cf210dccd012f34de857e20a504ccdb2ea',
        'focus': '직무별 추천 가치관 표의 디자인/UI·UX 행. 사용자 테스트를 바탕으로 디자인을 개선한 예시.',
        'what_to_explain': '처음에 어떤 안으로 진행했는지, 사용자 테스트에서 무엇을 새로 알았는지, 무엇을 바꾸거나 유지했고 그 이유가 무엇인지.',
        'design_basis': 'NCS 문제해결능력의 정보 수집 및 검증, 의사결정 수행 및 검토를 참고해 연결한 예시.',
    },
    'repeated-work-experience-v2-0': {
        'filename': 'question-07-repeat-work.png',
        'sha256': 'fc1d1a77f8449a2701cded2952ae7cde44c6fa93a181e41f0b79a8ce5e31d8a6',
        'focus': '자소서 성격 장단점 표의 예시 2 개발 직무 개선 버전. 준비에 시간이 걸려 먼저 실행하고 보완한 예시.',
        'what_to_explain': '같은 방식을 썼던 두 번의 결과가 어떻게 달랐는지, 무엇을 근거로 다음 업무에서 사용할 방식을 정했는지.',
        'design_basis': 'NCS 문제해결능력의 성찰 및 피드백을 참고해 연결한 예시.',
    },
}


def load(question_ids):
    """Return prompt metadata and verified bytes in matching question order."""
    guides, images = {}, {}
    for question_id, reference in REFERENCES.items():
        if question_id not in question_ids:
            continue
        try:
            with (IMAGE_DIRECTORY / reference['filename']).open('rb') as file:
                image = file.read(MAX_IMAGE_BYTES + 1)
        except OSError:
            image = b''
        if image and len(image) <= MAX_IMAGE_BYTES and sha256(image).hexdigest() == reference['sha256']:
            images[question_id] = image
        guides[question_id] = {key: value for key, value in reference.items() if key != 'sha256'}
        guides[question_id].update(file_ready=question_id in images, design_source=NCS_PROBLEM_SOLVING)
        if question_id in images:
            guides[question_id]['sha256'] = reference['sha256']
    return guides, images

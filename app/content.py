from __future__ import annotations

from copy import deepcopy


ORDINAL_LABELS = [
    "전혀 그렇지 않다",
    "그렇지 않다",
    "그렇지 않은 편이다",
    "그런 편이다",
    "그렇다",
    "매우 그렇다",
]

ORDERED_OPTIONS = [
    {"option_id": f"agreement-{position}", "label": label, "position": position}
    for position, label in enumerate(ORDINAL_LABELS, 1)
]


def _ordinal(item_id: str, behavior_id: str, prompt: str) -> dict:
    return {
        "item_id": item_id,
        "item_version": "1.0.0",
        "instructions_version": "1.0.0",
        "type": "ordinal_6",
        "prompt": prompt,
        "behavior_id": behavior_id,
        "scale_id": "agreement-6",
        "scale_version": "1.0.0",
        "ordered_options": deepcopy(ORDERED_OPTIONS),
        "time_limit_ms": 30_000,
    }


_B01_PROMPT = "공동 결정을 내리기 전에 팀원이 알고 있는 정보를 확인한다."

SURVEYS = [
    _ordinal("O-B01", "B01", _B01_PROMPT),
    _ordinal("O-B02", "B02", "개인 과제와 팀 과제가 겹치면 목표와 제약을 확인한 뒤 시간을 배분한다."),
    _ordinal("O-B03", "B03", "새 정보가 들어오면 처음 세운 계획을 다시 검토한다."),
    {
        "item_id": "P-B01",
        "item_version": "1.0.0",
        "instructions_version": "1.0.0",
        "type": "paired_perspective",
        "prompt": _B01_PROMPT,
        "behavior_id": "B01",
        "pair_id": "pair-b01-self-imagined",
        "paired_item_version": "1.0.0",
        "scale_id": "agreement-6",
        "scale_version": "1.0.0",
        "ordered_options": deepcopy(ORDERED_OPTIONS),
        "perspective_presentation_order": ["self", "imagined_others"],
        "prior_response_visible": True,
        "time_limit_ms": 45_000,
    },
    {
        "item_id": "S-B02",
        "item_version": "1.0.0",
        "instructions_version": "1.0.0",
        "type": "bipolar_slider",
        "prompt": "개인 과제와 팀 과제의 요구가 함께 있을 때 현재 더 가까운 선택을 표시해 주세요.",
        "behavior_id": "B02",
        "left_anchor": {"anchor_id": "personal-first", "label": "개인 과제의 제약을 먼저 살핀다"},
        "right_anchor": {"anchor_id": "team-first", "label": "팀 과제의 제약을 먼저 살핀다"},
        "min": -6,
        "max": 6,
        "step": 1,
        "initial_value": 0,
        "time_limit_ms": 30_000,
    },
    {
        "item_id": "R-UNMAPPED",
        "item_version": "1.0.0",
        "instructions_version": "1.0.0",
        "type": "top_k_rank",
        "prompt": "연습 환경을 고를 때 중요한 항목 세 개를 순서대로 선택해 주세요.",
        "behavior_id": None,
        "candidate_set_id": "practice-values",
        "candidate_set_version": "1.0.0",
        "requested_k": 3,
        "candidates": [
            {"option_id": "growth", "label": "새로운 것을 배울 기회", "version": "1.0.0"},
            {"option_id": "stability", "label": "예측 가능한 일정", "version": "1.0.0"},
            {"option_id": "autonomy", "label": "스스로 정할 수 있는 범위", "version": "1.0.0"},
            {"option_id": "helping", "label": "다른 사람을 도울 기회", "version": "1.0.0"},
            {"option_id": "recognition", "label": "기여를 인정받을 기회", "version": "1.0.0"},
        ],
        "display_order": ["growth", "stability", "autonomy", "helping", "recognition"],
        "time_limit_ms": 45_000,
    },
]


BEHAVIORS = [
    {
        "behavior_id": "B01",
        "behavior_version": "1.0.0",
        "name": "결정 전 정보 확인",
        "operational_definition": "결정을 확정하기 전에 다른 사람이 가진 과제 정보를 열어 확인한다.",
        "inclusions": ["결정 전에 제공된 팀원 정보 열기"],
        "exclusions": ["결정 뒤 정보 열기", "정보를 이해·동의·신뢰했다는 추론"],
        "context_requirements": ["정보 접근 기회", "결정 확정 시점", "이벤트 순서"],
    },
    {
        "behavior_id": "B02",
        "behavior_version": "1.0.0",
        "name": "제한 자원 배분",
        "operational_definition": "정해진 총자원 안에서 개인 과제와 팀 과제에 자원을 배분한다.",
        "inclusions": ["합법적 범위 안의 개인/팀 배분 확정"],
        "exclusions": ["팀 배분이 많을수록 좋다는 평가", "자기희생을 정답으로 보는 해석"],
        "context_requirements": ["총자원", "가능 범위", "보상 규칙", "결정 시점"],
    },
    {
        "behavior_id": "B03",
        "behavior_version": "1.0.0",
        "name": "새 정보 뒤 선택 재검토",
        "operational_definition": "새 정보가 제시된 뒤 수정 기회에서 기존 선택을 유지하거나 변경해 다시 확정한다.",
        "inclusions": ["새 정보 뒤 변경", "새 정보 뒤 의도적 유지"],
        "exclusions": ["새 정보 전에 일어난 변경", "변경 횟수에 대한 가점"],
        "context_requirements": ["새 정보 노출", "초기 결정", "수정 기회", "최종 결정"],
    },
]


MAPPINGS = [
    {
        "mapping_id": f"map-game-{behavior.lower()}",
        "version": "1.0.0-draft",
        "source_definition_id": "resource-bridge",
        "source_definition_version": "1.0.0",
        "source_kind": "game_event_rule",
        "behavior_id": behavior,
        "behavior_version": "1.0.0",
        "reason": reason,
        "observable_proxy": proxy,
        "preconditions": preconditions,
        "eligible_opportunity_rule": opportunity,
        "limitations": limitations,
        "permitted_uses": ["practice_question_generation", "game_observation_report", "evidence_comparison"],
        "practice_review_status": "draft",
        "validity_status": "provisional_unvalidated",
        "reviewer_type": None,
        "reviewer_id": None,
        "review_mode": None,
        "reviewed_at": None,
        "review_note": "독립 연습용 검토 전 초안",
    }
    for behavior, reason, proxy, preconditions, opportunity, limitations in [
        (
            "B01",
            "결정 전에 접근 가능한 팀원 정보 창을 여는 순서를 직접 기록한다.",
            "정보 접근 이벤트이며 이해·동의·존중의 직접 증거가 아니다.",
            ["main_round", "info_available", "decision_not_finalized"],
            "본 라운드에서 정보 창이 결정 전에 접근 가능하면 1회 적격 기회",
            ["열기만 관찰하며 읽거나 이해했는지는 알 수 없음", "결정 후 열기는 분자에서 제외"],
        ),
        (
            "B02",
            "고정된 총자원 안에서 사용자가 확정한 개인·팀 배분을 기록한다.",
            "게임 규칙 안의 자원 배분이며 일반적 협업 능력의 점수가 아니다.",
            ["main_round", "allocation_available", "legal_total_resources"],
            "본 라운드에서 0부터 총자원까지 합법적 배분을 확정할 수 있으면 1회 적격 기회",
            ["팀 몫이 크다고 더 좋지 않음", "선택 이유는 별도 자기보고"],
        ),
        (
            "B03",
            "새 정보가 실제로 제시된 뒤 수정 기회에서 유지 또는 변경한 결과를 기록한다.",
            "재검토 기회의 최종 선택이며 변경 자체의 우수성이나 동기를 뜻하지 않는다.",
            ["main_round", "initial_decision_exists", "new_information_revealed", "revision_available"],
            "본 라운드에서 초기 결정 뒤 새 정보와 수정 기회가 모두 제시되면 1회 적격 기회",
            ["유지도 적격 관찰이며 변경 분자는 0", "새 정보 전 변경은 귀속하지 않음"],
        ),
    ]
]


def _source_mapping(
    mapping_id: str,
    source_definition_id: str,
    source_kind: str,
    behavior_id: str,
    reason: str,
    proxy: str,
    preconditions: list[str],
    limitations: list[str],
    permitted_uses: list[str],
) -> dict:
    return {
        "mapping_id": mapping_id,
        "version": "1.0.0-draft",
        "source_definition_id": source_definition_id,
        "source_definition_version": "1.0.0",
        "source_kind": source_kind,
        "behavior_id": behavior_id,
        "behavior_version": "1.0.0",
        "reason": reason,
        "observable_proxy": proxy,
        "preconditions": preconditions,
        "eligible_opportunity_rule": "해당 원본이 submitted/asked_answered이고 버전과 소유권이 일치할 때만 적격",
        "limitations": limitations,
        "permitted_uses": permitted_uses,
        "practice_review_status": "draft",
        "validity_status": "provisional_unvalidated",
        "reviewer_type": None,
        "reviewer_id": None,
        "review_mode": None,
        "reviewed_at": None,
        "review_note": "독립 연습용 검토 전 초안",
    }


MAPPINGS.extend(
    [
        _source_mapping(
            "map-survey-o-b01", "O-B01", "survey_self_report", "B01",
            "결정 전 정보 확인에 대한 사용자의 순서형 자기보고 원문이다.",
            "자기보고 강도이며 실제 게임 행동이나 능력의 직접 관찰이 아니다.",
            ["submitted", "ordinal_label_preserved"],
            ["응답의 진실성 또는 안정된 성향을 인증하지 않음"],
            ["practice_question_generation", "original_response_report", "evidence_comparison"],
        ),
        _source_mapping(
            "map-survey-p-b01", "P-B01", "paired_perspective_self_report", "B01",
            "같은 사용자가 자기 관점과 상상한 타인 관점에서 결정 전 정보 확인을 보고한다.",
            "두 관점 모두 한 응답자의 자기보고이며 실제 제3자 평정이 아니다.",
            ["both_perspectives_submitted", "paired_version_matched"],
            ["관점 차이를 실제 주변 평가와의 오차로 해석하지 않음", "두 응답을 독립 표본으로 세지 않음"],
            ["practice_question_generation", "original_response_report", "evidence_comparison"],
        ),
        _source_mapping(
            "map-survey-o-b02", "O-B02", "survey_self_report", "B02",
            "제약 확인 뒤 개인·팀 과제에 시간을 배분한다는 순서형 자기보고 원문이다.",
            "자기보고 강도이며 실제 배분량의 직접 관찰이 아니다.",
            ["submitted", "ordinal_label_preserved"],
            ["높은 라벨을 관찰된 배분 능력으로 바꾸지 않음"],
            ["practice_question_generation", "original_response_report", "evidence_comparison"],
        ),
        _source_mapping(
            "map-survey-s-b02", "S-B02", "bipolar_preference_self_report", "B02",
            "개인 또는 팀 과제 중 어느 제약을 먼저 살필지에 대한 자체 양극 입력이다.",
            "제약 확인 순서의 자기보고 방향이며 실제 배분량이나 팀 몫 선호가 아니다.",
            ["submitted", "explicit_confirmation", "valid_step"],
            ["부호나 절댓값을 배분 능력으로 해석하지 않음", "게임 배분량과 직접 비교하지 않음"],
            ["practice_question_generation", "original_response_report"],
        ),
        _source_mapping(
            "map-survey-o-b03", "O-B03", "survey_self_report", "B03",
            "새 정보 뒤 계획 재검토에 대한 사용자의 순서형 자기보고 원문이다.",
            "자기보고 강도이며 실제 변경 여부의 직접 관찰이 아니다.",
            ["submitted", "ordinal_label_preserved"],
            ["계획 유지가 재검토 부재라는 뜻이 아님", "변경 횟수에 가점을 주지 않음"],
            ["practice_question_generation", "original_response_report", "evidence_comparison"],
        ),
        *[
            _source_mapping(
                f"map-interview-{behavior.lower()}", f"rubric-{behavior.lower()}", "interview_rubric", behavior,
                reason,
                "사용자가 타이핑한 경험 설명에서 명시적으로 인용 가능한 요소이며 경험의 진실성 검증이 아니다.",
                ["neutral_baseline_question", "asked_answered", "exact_quote_offsets"],
                ["구체적 답변도 실제 사건을 외부 검증하지 않음", "미언급을 행동 부재로 바꾸지 않음"],
                ["baseline_extraction", "practice_question_generation", "evidence_comparison", "original_response_report"],
            )
            for behavior, reason in [
                ("B01", "누구에게 어떤 정보를 확인했고 결정에 어떻게 반영했는지를 묻는 중립 면접 루브릭이다."),
                ("B02", "제한 자원의 배분 기준과 대안, 결과를 묻는 중립 면접 루브릭이다."),
                ("B03", "새 정보 뒤 선택을 유지 또는 변경한 내용과 이유를 묻는 중립 면접 루브릭이다."),
            ]
        ],
    ]
)

for _mapping_definition in MAPPINGS:
    _mapping_definition.update(
        {
            "version": "1.0.0",
            "practice_review_status": "approved_for_practice",
            "validity_status": "provisional_unvalidated",
            "reviewer_type": "ai_agent",
            "reviewer_id": "/root/domain_review_resume",
            "review_mode": "independent_reviewer",
            "reviewed_at": "2026-09-16T14:03:06Z",
            "review_note": "Read-only independent project-domain review of source-specific mappings; practice use only within permitted_uses, not psychometric validation. Exact survey direction, game opportunity/context, self-report limitations, and conditioned evidence separation remain required. Runtime aggregation/comparison defects reviewed separately.",
        }
    )


def _round(
    round_id: str,
    order: int,
    practice_or_main: str,
    title: str,
    info: str,
    new_info: str,
    initial_personal_min: int,
    initial_team_min: int,
    final_personal_min: int,
    final_team_min: int,
    prerequisite: str | None = None,
) -> dict:
    suffix = "practice" if practice_or_main == "practice" else f"main-{order}"
    return {
        "round_id": round_id,
        "round_version": "1.0.0",
        "order": order,
        "practice_or_main": practice_or_main,
        "title": title,
        "instructions": "10개의 자원을 개인 과제와 팀 과제에 나눈 뒤 새 정보를 확인하고 최종 선택을 확정하세요.",
        "total_resources": 10,
        "initial_requirements": {"personal_min": initial_personal_min, "team_min": initial_team_min, "prerequisite": prerequisite},
        "final_requirements": {"personal_min": final_personal_min, "team_min": final_team_min, "prerequisite": prerequisite},
        "result_calculation": "final personal/team allocation is compared with final_requirements minima; when a prerequisite exists, the team condition is met only if both the team minimum and prerequisite are met; the result is never converted to a personality score",
        "time_limit_ms": 90_000,
        "difficulty": "practice" if practice_or_main == "practice" else "standard",
        "information": {"information_id": f"info-{suffix}", "version": "1.0.0", "summary": "팀원 과제 정보는 선택해서 열 수 있습니다.", "text": info, "opened": False},
        "new_information": {
            "information_id": f"new-{suffix}",
            "version": "1.0.0",
            "text": new_info,
            "updated_requirements": {"personal_min": final_personal_min, "team_min": final_team_min, "prerequisite": prerequisite},
        },
        "reward_table_initial": [
            {"condition": f"초기 개인 배분이 {initial_personal_min} 이상", "reward": "개인 과제 조건 충족"},
            {"condition": f"초기 팀 배분이 {initial_team_min} 이상" + (f" 및 {prerequisite}" if prerequisite else ""), "reward": "팀 과제 조건 충족"},
        ],
        "reward_table_final": [
            {"condition": f"최종 개인 배분이 {final_personal_min} 이상", "reward": "개인 과제 조건 충족"},
            {"condition": f"최종 팀 배분이 {final_team_min} 이상" + (f" 및 {prerequisite}" if prerequisite else ""), "reward": "팀 과제 조건 충족"},
        ],
        "opportunities": [
            {"opportunity_id": f"opp-{suffix}-info", "behavior_id": "B01", "mapping_id": "map-game-b01", "eligible": practice_or_main == "main", "eligible_reason": "main_round" if practice_or_main == "main" else "practice_excluded"},
            {"opportunity_id": f"opp-{suffix}-allocation", "behavior_id": "B02", "mapping_id": "map-game-b02", "eligible": practice_or_main == "main", "eligible_reason": "main_round" if practice_or_main == "main" else "practice_excluded"},
            {"opportunity_id": f"opp-{suffix}-revision", "behavior_id": "B03", "mapping_id": "map-game-b03", "eligible": practice_or_main == "main", "eligible_reason": "main_round" if practice_or_main == "main" else "practice_excluded"},
        ],
    }


GAME = {
    "game_id": "resource-bridge",
    "game_version": "1.0.0",
    "rules_version": "1.0.0",
    "algorithm_version": "game-aggregation-1.0.0",
    "seed": "fixed-mvp-1",
    "instructions": "연습 라운드 뒤 세 본 라운드에서 제한 자원을 배분합니다.",
    "rounds": [
        _round("practice-1", 0, "practice", "연습: 자원 다리", "처음에는 개인 4개, 팀 4개 이상이 필요합니다.", "팀 과제의 필요 자원이 5개로 바뀌었습니다.", 4, 4, 4, 5),
        _round("main-1", 1, "main", "본 라운드 1: 균형 조건", "처음에는 개인 5개, 팀 5개 이상이 필요합니다.", "개인 과제의 최소 필요 자원이 4개로 바뀌었습니다.", 5, 5, 4, 5),
        _round("main-2", 2, "main", "본 라운드 2: 시간 조건", "처음에는 개인 4개, 팀 6개 이상이 필요합니다.", "팀 과제의 최소 필요 자원이 4개로 바뀌었습니다.", 4, 6, 4, 4),
        _round("main-3", 3, "main", "본 라운드 3: 선행 조건", "처음에는 개인 3개, 팀 4개 이상이 필요하며 개인 최소 조건이 팀 과제의 선행 조건입니다.", "개인 과제의 최소 필요 자원이 5개로 바뀌었습니다.", 3, 4, 5, 4, "개인 최소 조건을 충족해야 팀 과제 조건도 유효"),
    ],
}


QUESTIONS = [
    {
        "question_id": f"baseline-{behavior.lower()}",
        "question_version": "1.0.0",
        "question_text": text,
        "behavior_id": behavior,
        "target_behavior_ids": [behavior],
        "question_mode": "baseline",
        "asked_criteria": criteria,
        "question_prompt_version": "baseline-1.0.0",
        "rubric_id": f"rubric-{behavior.lower()}",
        "rubric_version": "1.0.0",
        "generated_from_evidence_refs": [],
        "disclosed_prior_information": [],
        "conditioned_on_prior_evidence": False,
        "selection_reason": "MVP에서 행동별 중립 기본 질문을 한 개씩 제시",
        "trigger_rule_id": "baseline-required",
        "trigger_rule_version": "1.0.0",
    }
    for behavior, text, criteria in [
        ("B01", "결정 전에 다른 사람이 가진 정보를 확인했던 경험을 설명해 주세요. 당시 상황과 본인 역할, 누구에게 무엇을 확인했고 판단에 어떻게 반영했는지, 결과와 배운 점을 함께 말해 주세요.", ["situation", "role", "other_information", "action", "reasoning", "result", "learning"]),
        ("B02", "개인 과제와 팀 과제 사이에서 제한된 시간이나 자원을 나눈 경험을 설명해 주세요. 당시 상황과 본인 역할, 선택 가능한 대안, 배분 기준과 실제 행동, 결과와 배운 점을 함께 말해 주세요.", ["situation", "role", "action", "reasoning", "result", "learning"]),
        ("B03", "새로운 정보를 받은 뒤 처음 선택을 유지하거나 바꾼 경험을 설명해 주세요. 당시 상황과 본인 역할, 새 정보, 재검토한 행동과 이유, 결과와 배운 점을 함께 말해 주세요.", ["situation", "role", "other_information", "action", "reasoning", "result", "learning"]),
    ]
]


DEFINITIONS = {
    "version": "1.0.0",
    "scale": {"scale_id": "agreement-6", "scale_version": "1.0.0", "ordered_options": deepcopy(ORDERED_OPTIONS)},
    "surveys": SURVEYS,
    "behaviors": BEHAVIORS,
    "mappings": MAPPINGS,
    "game": GAME,
    "questions": QUESTIONS,
    "runtime_mode": "mock",
}

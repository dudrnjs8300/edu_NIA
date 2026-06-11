너는 이 프로젝트의 Python 개발 보조자다.
먼저 프로젝트의 목적과 현재 단계의 범위를 이해한 뒤, 필요한 파일만 수정해줘.

# 프로젝트 목적

프로젝트명: Edu2WorkAI

이 프로그램은 AI 교육자료와 부서 업무자료를 연결하여,
“이번 교육에서 배운 AI 기술을 우리 부서 업무에 어떻게 적용할 수 있는가?”
라는 질문에 답하기 위한 로컬 기반 분석 도구다.

우리가 만들고 싶은 최종 흐름은 다음과 같다.

1. 교육자료 처리
- 교육 중 녹음한 음성/비디오를 별도 STT 도구로 텍스트화한다.
- 교육 PPT, 교육자료, 녹취 텍스트를 함께 정리한다.
- 교육에서 다룬 핵심 AI 개념을 추출한다.
  예: RAG, VectorDB, AI Agent, workflow automation, STT, OCR, 문서분석, 데이터 시각화 등

2. 부서 업무자료 처리
- NTIS에 공개된 연구과제별 연구결과보고서를 HWPX에서 Markdown으로 변환한 뒤 분석한다.
- 보고서에서 주요 연구내용, 실험방법, 연구결과, 산출물, 반복 업무, 데이터 유형을 추출한다.
- 여러 연도의 보고서를 정리하여 부서 업무 이력과 반복 업무 패턴을 만든다.

3. 교육내용과 업무자료 연결
- 교육에서 배운 AI 기술과 부서 업무자료에서 반복적으로 나타나는 업무를 연결한다.
- 최종적으로 “AI 활용 아이디어 카드”를 생성한다.
- 아이디어 카드는 문제, 업무자료 근거, 연결된 교육내용, 적용 가능한 자료, 기대효과, 구현 난이도, MVP 범위, 향후 확장, 한계 및 유의사항을 포함한다.

핵심 메시지:
교육을 듣고 끝내는 것이 아니라, 교육내용을 부서의 실제 업무자료와 연결해 실행 가능한 AI 활용 아이디어로 전환하는 도구를 만든다.

# 현재 개발 단계

현재는 1차 MVP 단계다.

이번 단계에서는 다음만 구현한다.
- TXT/MD 교육자료 읽기
- TXT/MD 연구결과보고서 읽기
- 규칙 기반 키워드 추출
- 규칙 기반 보고서 섹션 파싱
- 부서 업무지도 생성
- AI 활용 아이디어 카드 생성
- 최종 Markdown 보고서 초안 생성

이번 단계에서는 다음을 구현하지 않는다.
- 음성 STT 직접 구현
- 비디오 처리
- PPT 직접 파싱
- HWPX 직접 변환
- VectorDB 연동
- GUI
- Ollama/LLM 호출

Ollama와 LLM 연동은 다음 단계에서 붙일 예정이다.
지금은 반드시 LLM 없이 동작해야 한다.

# 현재 문제

CLI 명령은 실행된다.

python -m app.main init
python -m app.main process-education
python -m app.main process-reports
python -m app.main build-map
python -m app.main generate-ideas
python -m app.main export

하지만 산출물이 아직 dummy 수준이다.

문제 예시:
- education_concepts.json에 trailing comma가 있어 유효하지 않은 JSON이 생긴다.
- report_summaries.jsonl에 "dummy json response"가 들어간다.
- idea_cards.md, final_report_draft.md 등에 깨진 한글 문자열이 들어간다.
- 예: 援먯쑁湲고쉷, ?쒖슜, ?꾩씠?붿뼱
- 실제 입력 파일 내용을 반영한 분석이 부족하다.

# 수정 원칙

1. 모든 Python 파일과 출력 파일은 UTF-8로 처리한다.
2. 깨진 한글 문자열을 모두 제거한다.
3. dummy, placeholder, TODO 중심의 산출물을 만들지 않는다.
4. JSON은 반드시 유효해야 한다.
5. JSON 저장은 ensure_ascii=False, indent=2를 사용한다.
6. JSONL은 한 줄에 유효한 JSON 객체 하나씩 저장한다.
7. 현재 단계에서는 llm_client.py를 호출하지 않는다.
8. 향후 LLM으로 교체하기 쉽도록 규칙 기반 함수명은 *_rule_based 형태로 둔다.
9. 이미 있는 CLI 구조는 유지한다.
10. 프로젝트 전체를 새로 만들지 말고 필요한 모듈만 수정한다.
11. 입력 파일이 없어도 에러 없이 빈 기본 산출물을 생성한다.

# 수정 대상 파일

주로 아래 파일을 수정한다.

app/modules/education_processor.py
app/modules/report_parser.py
app/modules/department_mapper.py
app/modules/idea_generator.py
app/modules/exporter.py
app/utils/json_utils.py
필요하면 app/utils/text_utils.py
필요하면 app/pipeline.py

app/main.py의 CLI 구조는 가능하면 유지한다.

# 구현 요구사항

## 1. education_processor.py

입력:
workspace/01_education_raw 안의 .txt, .md 파일

출력:
workspace/02_education_processed/education_merged.md
workspace/02_education_processed/education_summary.md
workspace/02_education_processed/education_concepts.json

기능:
- .txt, .md 파일을 모두 읽는다.
- 파일명과 내용을 education_merged.md에 병합한다.
- 교육 텍스트에서 핵심 AI 키워드를 탐지한다.

탐지할 키워드:
RAG
VectorDB
AI Agent
workflow automation
STT
OCR
문서분석
데이터 시각화
자동화
보고서
요약
지식관리
프롬프트
생성형 AI
LLM
로컬 AI
embedding

동의어 처리:
벡터DB, 벡터 DB, vector db -> VectorDB
워크플로우, workflow -> workflow automation
에이전트, agent -> AI Agent
검색증강생성, 검색 증강 생성 -> RAG

education_concepts.json 스키마:
{
  "education_title": "AI 교육자료 분석",
  "source_files": [],
  "core_topics": [],
  "practical_methods": [
    {
      "method": "",
      "description": "",
      "possible_use": ""
    }
  ],
  "key_messages": [],
  "possible_applications": []
}

education_summary.md는 다음 섹션을 포함한다.
# 교육내용 요약
## 입력 파일
## 핵심 주제
## 주요 메시지
## 업무 적용 관점

## 2. report_parser.py

입력:
workspace/04_ntis_md 안의 .txt, .md 파일

출력:
workspace/05_department_analysis/report_summaries.jsonl

기능:
- 각 파일에서 파일명 또는 본문에서 4자리 연도를 추출한다.
- Markdown heading을 기준으로 섹션을 추출한다.
- heading이 없으면 키워드 기반으로 최소 정보를 채운다.

인식할 heading:
과제명
연구목표
연구 목적
목적
주요 연구내용
연구내용
실험방법
연구방법
방법
연구결과
결과
산출물
주요 산출물

report_summary 스키마:
{
  "source_file": "",
  "year": "",
  "project_title": "",
  "objective": "",
  "main_contents": [],
  "methods": [],
  "results": [],
  "outputs": [],
  "repeated_tasks": [],
  "data_types": [],
  "ai_opportunity_keywords": []
}

repeated_tasks 키워드:
보고서 작성
분석결과표 작성
문헌조사
데이터 정리
유전체 분석
시각화
발표자료 작성
논문 작성
연구성과 정리
감시자료 정리

data_types 키워드:
WGS
AST
MLST
AMR gene
plasmid
genome assembly
연구보고서
발표자료
엑셀 데이터
논문
균주 정보
실험결과
유전체 데이터

ai_opportunity_keywords 후보:
자동 요약
결과표 정리
문서검색
RAG
VectorDB
보고서 초안 생성
데이터 시각화
업무자료 검색
연구성과 지식맵
AI 아이디어 진단

## 3. department_mapper.py

입력:
workspace/05_department_analysis/report_summaries.jsonl

출력:
workspace/05_department_analysis/department_work_map.json
workspace/05_department_analysis/department_timeline.md

department_work_map.json 스키마:
{
  "department_work_summary": "",
  "timeline": [
    {
      "year": "",
      "project_titles": [],
      "main_work": [],
      "methods": [],
      "outputs": []
    }
  ],
  "major_work_areas": [],
  "repeated_work_patterns": [],
  "data_assets": [],
  "automation_candidates": []
}

기능:
- timeline은 연도별로 묶는다.
- repeated_tasks, data_types, ai_opportunity_keywords는 전체 보고서에서 모아 중복 제거한다.
- department_timeline.md는 깨지지 않는 한글로 작성한다.

## 4. idea_generator.py

입력:
workspace/02_education_processed/education_concepts.json
workspace/05_department_analysis/department_work_map.json

출력:
workspace/06_matching_output/idea_cards.json
workspace/06_matching_output/idea_cards.md

기능:
최소 3개의 아이디어 카드를 생성한다.

idea_cards.json 스키마:
[
  {
    "idea_title": "",
    "problem": "",
    "evidence_from_work_materials": [],
    "linked_education_topics": [],
    "applicable_data_or_documents": [],
    "expected_effect": "",
    "implementation_difficulty": "낮음|중간|높음",
    "mvp_scope": "",
    "future_expansion": "",
    "risk_or_limitation": ""
  }
]

기본 아이디어 후보:
1. 교육내용-업무자료 연계 AI 활용 아이디어 진단 도구
2. 연구결과보고서 기반 부서 지식맵 생성 도구
3. 보고서·데이터 기반 업무 자동화 후보 탐색 도구
4. 교육 녹취 기반 AI 교육내용 구조화 도구
5. 연구성과 기반 신규 과제 기획 지원 도구

idea_cards.md 형식:
# AI 활용 아이디어 카드

## 1. 아이디어명
- 문제:
- 업무자료 근거:
- 연결된 교육내용:
- 적용 가능한 자료:
- 기대효과:
- 구현 난이도:
- MVP 범위:
- 향후 확장:
- 한계 및 유의사항:

## 5. exporter.py

입력:
education_summary.md
education_concepts.json
report_summaries.jsonl
department_work_map.json
idea_cards.md
idea_cards.json

출력:
workspace/07_final_report/final_input_packet.md
workspace/07_final_report/final_report_draft.md

final_report_draft.md 섹션:
# 최종 보고서 초안
## 1. 추진 배경
## 2. 교육내용 요약
## 3. 부서 업무자료 분석 결과
## 4. AI 활용 아이디어
## 5. 향후 계획

## 6. json_utils.py

다음 함수를 안정적으로 구현한다.
read_json(path, default=None)
write_json(path, data)
read_jsonl(path)
write_jsonl(path, rows)
append_jsonl(path, row)

모든 함수는 UTF-8을 사용한다.
write_json은 ensure_ascii=False, indent=2를 사용한다.

# 테스트 입력 예시

workspace/01_education_raw/sample_education.md

# AI 보수교육 메모
이번 교육에서는 RAG, VectorDB, AI Agent, workflow automation의 개념을 학습하였다.
RAG는 외부 문서나 데이터에서 관련 근거를 검색한 뒤 답변을 생성하는 방식이다.
VectorDB는 문서나 데이터의 의미를 벡터로 저장하여 유사한 정보를 검색하는 데 사용된다.
AI Agent는 사용자의 요청에 따라 필요한 도구를 선택하고, 여러 단계를 수행하는 자동화 도우미로 활용될 수 있다.
교육을 통해 단순 문서작성보다, 업무자료와 데이터를 연결하여 반복 업무를 줄이고 새로운 업무 개선 아이디어를 도출하는 것이 중요하다고 느꼈다.

workspace/04_ntis_md/sample_report_2024.md

# 2024년 연구결과보고서

## 과제명
항생제 내성균 유전체 분석 기반 감시 연구

## 연구목표
국내 항생제 내성균의 유전체 특성을 분석하고, 내성기전과 유행 클론을 파악한다.

## 주요 연구내용
- 항생제 내성균 분리주 수집
- 전장유전체염기서열 분석
- MLST, AMR gene, plasmid replicon 분석
- 분석결과표 및 연구보고서 작성

## 실험방법
균주 배양, 항생제 감수성시험, DNA 추출, WGS, genome assembly, AMRFinderPlus, MLST 분석을 수행하였다.

## 연구결과
주요 내성유전자와 sequence type을 확인하였고, 일부 균주는 특정 고위험 클론과 관련성이 있는 것으로 분석되었다.

## 산출물
- 분석결과표
- 연구결과보고서
- 발표자료
- 논문 초안

# 검증 명령

수정 후 아래 명령이 모두 에러 없이 실행되어야 한다.

python -m app.main init
python -m app.main process-education
python -m app.main process-reports
python -m app.main build-map
python -m app.main generate-ideas
python -m app.main export

산출물에는 깨진 한글이 없어야 한다.
JSON은 반드시 유효해야 한다.
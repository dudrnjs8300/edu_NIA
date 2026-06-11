# Edu2WorkAI

교육자료와 부서 업무자료를 함께 분석해서, 실제 업무에 적용할 수 있는 AI 활용 아이디어와 보고서 초안을 만드는 도구입니다.

## 입력 파일 위치

- 교육자료: `workspace/01_education_raw`
- 보고서/업무자료: `workspace/04_ntis_md`
- NTIS CSV: `workspace/03_ntis_raw`

## 지원 파일 형식

- 교육자료: `.txt`, `.md`, `.pptx`, `.ppt`, `.mp3`, `.wav`, `.m4a`, `.mp4`, `.aac`, `.flac`, `.hwpx`, `.hwp`
- 보고서: `.txt`, `.md`
- NTIS: `.csv`

## 실행 방법

설치:

```bash
pip install -r requirements.txt
```

CLI 초기화:

```bash
python -m app.main init
```

전체 실행:

```bash
python -m app.main run-all
```

개별 실행:

```bash
python -m app.main transcribe-audio
python -m app.main extract-ppt
python -m app.main convert-docs
python -m app.main process-education
python -m app.main process-reports
python -m app.main build-map
python -m app.main generate-ideas
python -m app.main export
```

GUI 실행:

```bash
python -m app.gui
```

배치 파일:

- `run.bat` → GUI 실행
- `run_all.bat` → CLI 전체 실행
- `check_project.bat` → 사전 점검

## OpenAI API Key 설정

`config.json`에는 실제 키를 넣지 않습니다. 대신 환경변수로 설정합니다.

예:

```bash
set OPENAI_API_KEY=your_api_key_here
```

## LLM 실패 시 동작

API 호출이 429(과도한 요청) 또는 인증/쿼터 문제로 실패하면, Edu2WorkAI는 그 실행에서는 LLM 호출을 중단하고 rule-based fallback으로 계속 진행합니다.

## 결과 파일 위치

- 교육 요약: `workspace/02_education_processed/education_summary.md`
- 교육 개념 JSON: `workspace/02_education_processed/education_concepts.json`
- 부서 업무 맵: `workspace/05_department_analysis/department_work_map.json`
- 아이디어 카드: `workspace/06_matching_output/idea_cards.json`, `idea_cards.md`
- 최종 보고서: `workspace/07_final_report`

## HWPX 변환 제한사항

- HWPX는 우선 안전한 XML 기반 추출을 시도합니다.
- Kordoc MCP 연결은 다음 단계에서 붙일 수 있도록 인터페이스만 준비되어 있습니다.
- `.hwp`는 현재 직접 변환이 어려울 수 있으며, 안내 메시지가 출력됩니다.

## 참고

- `config.json`의 LLM 설정은 API 키 문자열이 아니라 환경변수 이름을 사용합니다.
- `workspace` 폴더는 `init` 또는 `run-all` 실행 시 생성됩니다.
- PyInstaller exe 패키징은 다음 단계에서 진행할 예정입니다.

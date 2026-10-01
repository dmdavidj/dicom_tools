RP Proton Converter
===================
RayStation 탄소선 RT Ion Plan(RadiationType=ION)을 ProKnow에 업로드할 수 있는 형태로 변환합니다.

사용법
------
1) dist\rp_proton_converter.exe 위에 RP 파일이나 폴더를 드래그 앤 드롭
   또는 exe를 더블클릭한 뒤 파일/폴더 경로를 입력
2) 결과 파일 위치: 원본 폴더\fixed\<원본이름>_proton.dcm
   - RT Ion Plan이 아닌 파일(RD, RS, CT 등)은 자동으로 건너뜁니다.
   - 원본 파일은 수정하지 않습니다.

변경 내용
---------
- Transfer Syntax: Implicit VR -> Explicit VR Little Endian
- Ion Beam Radiation Type: ION -> PROTON
  (Radiation Mass Number / Atomic Number / Charge State 삭제)
- 비어 있는 Cumulative Dose Reference Coefficient = CMW / Final CMW 로 채움
- 사설 태그 삭제
- SOP Instance UID, 에너지/스팟/MU/아이소센터 등 물리 데이터는 그대로 유지

주의: 변환 파일은 ProKnow 평가 전용입니다. 치료/QA/다른 TPS에는 원본을 사용하세요.

다시 빌드하기 (Python 필요)
---------------------------
  python -m venv venv
  venv\Scripts\pip install pydicom==3.0.2 pyinstaller
  venv\Scripts\pyinstaller --onefile --console --name rp_proton_converter rp_proton_converter.py

requirement 변경사항

streamlit>=1.28.0
 <br />
fastapi>=0.104.0
 <br />
uvicorn[standard]>=0.24.0
 <br />
python-multipart>=0.0.6
 <br />
python-jose[cryptography]>=3.3.0
 <br />
passlib[bcrypt]>=1.7.4



# 모듈 추가 업그레이드 11.14 (fastapi오류로 인한)

[notice] A new release of pip is available: 25.2 -> 25.3
[notice] To update, run: python.exe -m pip install --upgrade pip

python.exe -m pip install --upgrade pip

pip install passlib
pip install fastapi
pip install jose
pip install --upgrade python-jose
pip install --upgrade -r requirements.txt


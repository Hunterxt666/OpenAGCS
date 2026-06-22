# remote server up script
cd /root/Communication
redis-cli FLUSHALL
echo "Flush redis successfully"
python3 -m pip install -r requirements.txt
PYTHONPATH=/root/Communication python3 /root/Communication/remote_backend_api.py
echo "Run remote server successfully"

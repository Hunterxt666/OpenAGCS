# local server up script
cd ~/Communication
redis-cli FLUSHALL
echo "Flush redis successfully"
~/testvenv/bin/python -m pip install -r requirements.txt
PYTHONPATH=~/Communication ~/testvenv/bin/python ~/Communication/local_backend_api.py &
echo "Run local upload successfully"
sleep 20
curl http://127.0.0.1:26969/startUpload || echo "Request /StartUpload failed!"



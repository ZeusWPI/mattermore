# Mattermore
Mattermost integrations

## Installation guide

1. Clone this repository
```
git clone ssh://git@git.zeus.gent:2222/mattermost/mattermore.git
cd mattermore
```
2. Create a virtual environment
```
virtualenv -p python3 venv
```
3. Install the pip requirements
```
./venv/bin/pip install -r requirements.txt
```
4. Create the database
```
./venv/bin/python setup_database.py
```
5. Start the server
```
./venv/bin/python run_dev.py
```

*migrations*


## testing

```
pip3 install flake8
flake8 . --count --max-complexity=10 --max-line-length=127 --statistics --exclude ./migrations/
```

from flask import Flask, request
import subprocess

app = Flask(__name__)

@app.route('/payload', methods=['POST'])
def webhook():
    # Optional: Verify GitHub secret or repo name here
    subprocess.Popen(["/home/ec2-user/your-repo/deploy.sh"])
    return "Deployment triggered", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=4000)

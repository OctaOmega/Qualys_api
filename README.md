# Qualys CertView Sync App

## Setup

1. **Python Environment**
   ```powershell
   py -m venv venv
   .\venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configuration**
   - Copy `.env.example` to `.env`
   - Fill in your Qualys API URL and Credentials in `.env`
   ```
   QUALYS_INTERNAL_AUTH_PAYLOAD={"username": "your_user", "password": "your_password"}
   ```

## Running the App

```powershell
flask run
```
Access the UI at: http://127.0.0.1:5000

## Usage
1. Click **Start Full Sync** to begin fetching from 1900.
2. Observe the status card updates.
3. Click **Sync Again (Resume)** if interrupted.
4. Use **Export to Excel** to download the data.

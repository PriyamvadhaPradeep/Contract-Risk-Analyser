Contract Risk Analyzer:
The Contract Risk Analyzer is a Streamlit-based web application designed to assist legal and commercial teams in rapidly reviewing and analyzing contracts (MSAs, SOWs) for key terms, risks, and mitigation strategies.

Utilizing the Gemini API, the application performs a multi-stage, structured analysis:

Extracts key clauses from the uploaded document (PDF, DOCX, TXT).

Groups the findings under 8 fixed commercial/legal risk buckets (e.g., Services & Scope, Commercials & Pricing).

Categorizes identified risks with a RAG (Red/Amber/Green) rating based on a standardized matrix.

Generates a comprehensive dashboard including a Weighted Contract Risk Index (WCRI) score and top risks, all presented in a visually structured manner.

✨ Features:
File Upload Support: Analyze contracts in PDF, DOCX, or plain TXT format.

Structured Analysis: Findings are mapped to 8 standard risk buckets.

Risk Categorization: Provides RAG-coded tables of identified risks with clause references.

Interactive Dashboard: Displays a WCRI score, risk counts, and commercial snapshots.

Text Wrapping: The detailed risk tables are styled to ensure long text wraps properly within cells for easy readability.

⚙️ Setup and Installation
Prerequisites
Python: Python 3.8+

API Key: A valid Gemini API Key.

Local Installation
Clone the repository:

git clone [YOUR_REPOSITORY_URL]
cd contract-risk-analyzer

Create a virtual environment (Recommended):

python -m venv venv
source venv/bin/activate  # On Windows, use: .\venv\Scripts\activate

Install dependencies:
The application relies on the following packages, which are listed in your requirements.txt:

pip install -r requirements.txt

Set up the API Key:
Create a file named .env in the root directory of the project and add your Gemini API Key:

GEMINI_API_KEY="YOUR_ACTUAL_GEMINI_API_KEY_HERE"

Running Locally
Execute the Streamlit command from your project root:

streamlit run app.py

The application will automatically open in your web browser, typically at http://localhost:8501.

🚀 Deployment (Streamlit Community Cloud)
This application is best deployed using the Streamlit Community Cloud, as it requires a running Python server (it cannot be deployed using static hosting services like GitHub Pages).

Commit Files: Ensure app.py and requirements.txt are pushed to your GitHub repository.

Configure Secrets: When deploying the app on Streamlit Community Cloud:

Navigate to your app settings.

Add the GEMINI_API_KEY as a secret in the format:

GEMINI_API_KEY="YOUR_ACTUAL_API_KEY"

Launch: Select the repository and main file (app.py) to launch the app.

📂 Project Files:

app.py
The main Streamlit application script containing all UI, logic, and Gemini API calls for contract analysis.

requirements.txt
Lists all necessary Python dependencies for the project.

.env
Used to securely store the GEMINI_API_KEY.

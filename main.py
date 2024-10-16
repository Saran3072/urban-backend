from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import uvicorn

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # List the frontend's URL here
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods (GET, POST, PUT, DELETE, etc.)
    allow_headers=["*"],  # Allow all headers
)

# In-memory storage for users
users_db = []
reports_db = []

# Pydantic model for user registration data
class User(BaseModel):
    name: str
    email: str  # Validates that the input is a properly formatted email address
    password: str
    role: str  # 'user' or 'authority'
    phone: str
    location: str

class UserLogin(BaseModel):
    email: str
    password: str

class Report(BaseModel):
    email: str
    type: str  # 'authority' or 'community'
    category: Optional[str] = None  # Required only if type is 'authority'
    issue: str
    description: str
    location: str
    photo: Optional[str] = None
    alertLevel: Optional[str] = None  # Required only if type is 'community'

class ReportOut(BaseModel):
    id: int
    title: str
    category: str
    location: str
    seriousness: str
    description: str

class UserStats(BaseModel):
    totalReports: int
    resolvedReports: int
    unresolvedReports: int

class ReportHistoryItem(BaseModel):
    id: int
    title: str
    category: str
    status: str

class UserDashboardResponse(BaseModel):
    userStats: UserStats
    reportHistory: List[ReportHistoryItem]
    notifications: List[str]

class GlobalStats(BaseModel):
    totalReports: int
    resolvedReports: int
    unresolvedReports: int
    highPriorityReports: int

class IssueByCategory(BaseModel):
    category: str
    count: int

class IssueBySeriousness(BaseModel):
    seriousness: str
    count: int

class IssueManagementItem(BaseModel):
    id: int
    title: str
    category: str
    date: str
    seriousness: str
    status: str

class AuthorityDashboardResponse(BaseModel):
    globalStats: GlobalStats
    issuesByCategory: List[IssueByCategory]
    issuesBySeriousness: List[IssueBySeriousness]
    issueList: List[IssueManagementItem]

# Register a new user
@app.post("/register")
def register_user(user: User):
    # Check if the email is already in use
    if any(u['email'] == user.email for u in users_db):
        raise HTTPException(status_code=400, detail="User with this email already exists")
    
    # Store the new user in the in-memory database
    users_db.append(user.dict())
    return {"message": "User registered successfully"}

# Login Route
@app.post("/login")
def login_user(user: UserLogin):
    # Search for user in the in-memory database
    found_user = next((u for u in users_db if u['email'] == user.email), None)
    
    # Check if user exists and password matches
    if not found_user or found_user['password'] != user.password:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Successful login
    return {
        "message": "Login successful",
        "user": {
            "name": found_user['name'],
            "email": found_user['email'],
            "role": found_user['role'],
            "location": found_user['location']
        }
    }

# Endpoint to submit a report
@app.post("/report")
def submit_report(report: Report):
    # Find the user in the database to confirm email exists
    if not any(user['email'] == report.email for user in users_db):
        raise HTTPException(status_code=404, detail="User not found")

    # Validate required fields based on report type
    if report.type == 'authority' and not report.category:
        raise HTTPException(status_code=400, detail="Category is required for authority reports")
    if report.type == 'community' and not report.alertLevel:
        raise HTTPException(status_code=400, detail="Alert level is required for community alerts")

    # Store the report in the in-memory reports database
    reports_db.append(report.dict())
    return {"message": "Report submitted successfully"}

@app.get("/reports", response_model=List[ReportOut])
def get_all_reports():
    # Transform reports_db to match the output format
    issues_data = [
        {
            "id": index + 1,
            "title": report['issue'],
            "category": report['category'],
            "location": report['location'],
            "seriousness": report.get('seriousness', "Moderate"),  # Default seriousness level if none provided
            "description": report['description'],
        }
        for index, report in enumerate(reports_db)
    ]
    return issues_data

from fastapi import Query

# Endpoint to retrieve user dashboard data
@app.get("/user-dashboard", response_model=UserDashboardResponse)
def get_user_dashboard(email: str = Query(..., description="Email of the user")):
    # Filter reports by user email
    user_reports = [report for report in reports_db if report['email'] == email]
    
    # Calculate statistics
    total_reports = len(user_reports)
    resolved_reports = sum(1 for report in user_reports if report.get("status") == "Resolved")
    unresolved_reports = total_reports - resolved_reports

    user_stats = UserStats(
        totalReports=total_reports,
        resolvedReports=resolved_reports,
        unresolvedReports=unresolved_reports
    )

    # Prepare report history data
    report_history = [
        ReportHistoryItem(
            id=index + 1,
            title=report['issue'],
            category=report['category'],
            status=report.get("status", "Unresolved")
        )
        for index, report in enumerate(user_reports)
    ]

    # Generate notifications based on report statuses
    notifications = [
        f"Your report '{report['issue']}' has been marked as resolved."
        for report in user_reports if report.get("status") == "Resolved"
    ]

    # Compile the full response
    return UserDashboardResponse(
        userStats=user_stats,
        reportHistory=report_history,
        notifications=notifications
    )

# Endpoint to retrieve data for the Authority Dashboard
@app.get("/authority-dashboard", response_model=AuthorityDashboardResponse)
def get_authority_dashboard():
    # Calculate global statistics
    total_reports = len(reports_db)
    resolved_reports = sum(1 for report in reports_db if report.get("status") == "Resolved")
    unresolved_reports = total_reports - resolved_reports
    high_priority_reports = sum(1 for report in reports_db if report.get("seriousness") in ["High", "Critical"])

    global_stats = GlobalStats(
        totalReports=total_reports,
        resolvedReports=resolved_reports,
        unresolvedReports=unresolved_reports,
        highPriorityReports=high_priority_reports
    )

    # Count issues by category
    category_counts = {}
    for report in reports_db:
        category = report.get("category", "Other")
        category_counts[category] = category_counts.get(category, 0) + 1

    issues_by_category = [
        IssueByCategory(category=category, count=count)
        for category, count in category_counts.items()
    ]

    # Count issues by seriousness level
    seriousness_counts = {"Low": 0, "Moderate": 0, "High": 0, "Critical": 0}
    for report in reports_db:
        seriousness = report.get("seriousness", "Moderate")
        seriousness_counts[seriousness] += 1

    issues_by_seriousness = [
        IssueBySeriousness(seriousness=seriousness, count=count)
        for seriousness, count in seriousness_counts.items()
    ]

    # Prepare the issue management list
    issue_list = [
        IssueManagementItem(
            id=index + 1,
            title=report['issue'],
            category=report['category'],
            date=report['date'],
            seriousness=report.get("seriousness", "Moderate"),
            status=report.get("status", "Unresolved")
        )
        for index, report in enumerate(reports_db)
    ]

    # Compile the full response
    return AuthorityDashboardResponse(
        globalStats=global_stats,
        issuesByCategory=issues_by_category,
        issuesBySeriousness=issues_by_seriousness,
        issueList=issue_list
    )

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
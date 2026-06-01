from fastapi import FastAPI, Form, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
import httpx
from bs4 import BeautifulSoup
import asyncio
import urllib3
import logging

# Suppress the insecure request warnings caused by verify=False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Set up simple logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI App
app = FastAPI(title="SIMATS Result Hub")

# Serve static files
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def index():
    return FileResponse('static/index.html')

@app.get("/style.css")
async def style():
    return FileResponse('static/style.css')

@app.get("/script.js")
async def script():
    return FileResponse('static/script.js')

@app.get("/favicon.ico")
async def favicon():
    return FileResponse('static/favicon.ico')  # Or return a 204 if you don't have one

@app.post("/api/login")
async def login(username: str = Form(...), password: str = Form(...)):
    url = "https://arms.sse.saveetha.com/Login.aspx"
    
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "accept-language": "en-US,en;q=0.5",
        "cache-control": "no-cache",
        "content-type": "application/x-www-form-urlencoded",
        "origin": "https://arms.sse.saveetha.com",
        "pragma": "no-cache",
        "referer": "https://arms.sse.saveetha.com/Login.aspx",
        "upgrade-insecure-requests": "1",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
    }

    try:
        # We use httpx.AsyncClient with follow_redirects=False for the POST
        # and verify=False to ignore SSL warnings.
        async with httpx.AsyncClient(verify=False, headers=headers) as client:
            # Step 1: GET request
            response_get = await client.get(url, timeout=15.0)
            response_get.raise_for_status()
            
            # Parse HTML
            soup = BeautifulSoup(response_get.text, 'html.parser')
            
            viewstate = soup.find(id="__VIEWSTATE")
            viewstategenerator = soup.find(id="__VIEWSTATEGENERATOR")
            eventvalidation = soup.find(id="__EVENTVALIDATION")
            
            if not viewstate or not eventvalidation:
                return JSONResponse(status_code=500, content={"detail": "Could not find ASP.NET hidden fields on the login page."})
                
            payload = {
                "__VIEWSTATE": viewstate.get("value", ""),
                "__VIEWSTATEGENERATOR": viewstategenerator.get("value", "") if viewstategenerator else "",
                "__EVENTVALIDATION": eventvalidation.get("value", ""),
                "txtusername": username,
                "txtpassword": password,
                "btnlogin": "Login"
            }
            
            # Use the cookies from the GET request
            cookies = response_get.cookies
            
            # Step 2: POST request
            response_post = await client.post(url, data=payload, cookies=cookies, follow_redirects=False, timeout=15.0)
            
            # Extract the ASP.NET_SessionId cookie from the POST response or the client's current cookie jar
            session_id = client.cookies.get("ASP.NET_SessionId", domain="arms.sse.saveetha.com") or response_post.cookies.get("ASP.NET_SessionId")
            
            if response_post.status_code == 302:
                 return JSONResponse(content={"success": True, "ASP.NET_SessionId": session_id, "message": "Login successful!"})
                 
            if response_post.status_code == 200:
                 if "Invalid Username" in response_post.text or "Invalid" in response_post.text:
                     return JSONResponse(status_code=401, content={"detail": "Invalid Username or Password"})
                 return JSONResponse(content={"success": True, "ASP.NET_SessionId": session_id, "message": "Login appears successful!"})
                 
            return JSONResponse(status_code=401, content={"detail": "Login failed or unexpected status code."})
                 
    except httpx.RequestError as e:
        return JSONResponse(status_code=502, content={"detail": f"API request failed: {str(e)}"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": f"An error occurred: {str(e)}"})


async def fetch_api3(client: httpx.AsyncClient, month_id: str):
    """Fetch subjects for a given month."""
    url = f"https://arms.sse.saveetha.com/Handler/Controller.ashx?Page=CoursebyMonth&Mode=PublishCoursebyMonthNew&Monthyear={month_id}"
    resp = await client.get(url, timeout=15.0)
    return month_id, resp.json().get("Table", [])


async def process_course(client: httpx.AsyncClient, course_info: dict, subject_ids: list, username: str):
    """Fetch marks for a specific course/subject_ids."""
    try:
        user_clean = str(username).strip().lower()
        
        for subject_id in subject_ids:
            # API 4
            api4_url = f"https://arms.sse.saveetha.com/Handler/Controller.ashx?Page=ResultView&Mode=NewResultViewFaculty&Coursename={subject_id}"
            resp4 = await client.get(api4_url, timeout=15.0)
            api4_data = resp4.json().get("Table", [])
            
            view_id = None
            for student in api4_data:
                reg_clean = str(student.get("RegNo", "")).strip().lower()
                if reg_clean == user_clean or reg_clean.startswith(user_clean) or user_clean.startswith(reg_clean):
                    view_id = student.get("ViewId")
                    break
                    
            if view_id:
                # API 5
                api5_url = f"https://arms.sse.saveetha.com/Handler/Controller.ashx?Page=ViewMarks&Mode=MarkSplitbyId&Id={subject_id}&Id2={view_id}"
                resp5 = await client.get(api5_url, timeout=15.0)
                api5_data = resp5.json().get("Table", [])
                
                return {"course": course_info, "marks": api5_data, "error": None}
        
        return {"course": course_info, "marks": None, "error": f"View ID not found (searched across {len(subject_ids)} subject sections)"}
    except Exception as e:
        return {"course": course_info, "marks": None, "error": str(e)}


@app.post("/api/fetch-marks")
async def fetch_marks(username: str = Form(...), session_id: str = Form(...)):
    
    headers = {
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    cookies = {"ASP.NET_SessionId": session_id}
    
    try:
        # Use a single httpx AsyncClient session for all requests
        async with httpx.AsyncClient(verify=False, headers=headers, cookies=cookies) as client:
            
            # API 1
            api1_url = "https://arms.sse.saveetha.com/Handler/Student.ashx?Page=CourseEnroll&Mode=GetResult&Id=0"
            resp1 = await client.get(api1_url, timeout=15.0)
            courses = resp1.json().get("Table", [])
            
            # API 2
            api2_url = "https://arms.sse.saveetha.com/Handler/Controller.ashx?Page=MonthYear&Mode=MonthYearNew"
            resp2 = await client.get(api2_url, timeout=15.0)
            month_years = resp2.json().get("Table", [])
            
            month_map = {item["Value"]: item["Id"] for item in month_years}
            
            unique_months = set()
            for c in courses:
                mv = c.get("MonthYearValue")
                if mv in month_map:
                    unique_months.add(month_map[mv])
                    
            # Fetch API 3 for all unique months concurrently
            api3_tasks = [fetch_api3(client, mid) for mid in unique_months]
            api3_results = await asyncio.gather(*api3_tasks, return_exceptions=True)
            
            api3_cache = {}
            for res in api3_results:
                if isinstance(res, tuple):
                    mid, data = res
                    api3_cache[mid] = data
                else:
                    logger.error(f"Error fetching API 3: {res}")
                    
            # Build course to subject mapping
            course_subject_map = []
            for c in courses:
                mv = c.get("MonthYearValue")
                if mv not in month_map: continue
                month_id = month_map[mv]
                
                subject_ids = []
                for sub in api3_cache.get(month_id, []):
                    if sub["SubjectCode"] == c["CourseCode"]:
                        subject_ids.append(sub["SubjectId"])
                        
                if subject_ids:
                    course_subject_map.append((c, subject_ids))
                    
            # Fetch all marks concurrently
            marks_tasks = [process_course(client, c, sids, username) for c, sids in course_subject_map]
            final_data = await asyncio.gather(*marks_tasks, return_exceptions=True)
            
            # Filter out exceptions from gather and ensure valid dict structure
            processed_data = []
            for item in final_data:
                if isinstance(item, Exception):
                    logger.error(f"Error processing course: {item}")
                    continue
                processed_data.append(item)
                    
            # Sort data by Course Name for consistency
            processed_data.sort(key=lambda x: x["course"].get("CourseName", ""))
                    
            return JSONResponse(content={"success": True, "data": processed_data})
            
    except Exception as e:
        logger.exception("Failed to fetch detailed marks")
        return JSONResponse(status_code=500, content={"detail": f"Failed to fetch detailed marks: {str(e)}"})

if __name__ == "__main__":
    import uvicorn
    # Enable running via `python main.py` directly for convenience
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)

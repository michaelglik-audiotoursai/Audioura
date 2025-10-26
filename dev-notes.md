# Development Notes & Tips

## Docker & Containers

### PostgreSQL Container Access
- **Container Name**: development-postgres-2-1
- **Port**: 5433:5432
- **Username**: admin
- **Password**: password123
- **Database**: audiotours

**How to connect:**
1. Docker Desktop → Container → Exec tab
2. Run: `psql -U admin -d audiotours`

**Useful PostgreSQL commands:**
- `\dt` - show all tables
- `\d table_name` - show table schema
- `SELECT * FROM table_name LIMIT 5;` - view sample records
- `\l` - list all databases
- `\q` - quit

**IMPORTANT PostgreSQL Syntax Rules:**
- **ALL SQL commands MUST end with semicolon (;)**
- If no output appears, check if you forgot the semicolon
- Meta-commands (starting with \) do NOT need semicolons
- Examples:
  - ✅ `SELECT * FROM users;` (with semicolon)
  - ❌ `SELECT * FROM users` (missing semicolon - will be ignored)
  - ✅ `\dt` (meta-command, no semicolon needed)

**Find credentials:** `env | grep -i postgres`

---

## Python Development

### Virtual Environments
- Create: `python -m venv venv`
- Activate (Windows): `venv\Scripts\activate`
- Deactivate: `deactivate`

### Common Commands
- Install requirements: `pip install -r requirements.txt`
- Freeze dependencies: `pip freeze > requirements.txt`

---

## Audio Tours Project

### Services
- **Tour Generator**: http://localhost:5000
- **Tour Processor**: http://localhost:5001

### File Structure
- Text generation → Audio conversion → HTML creation → Netlify deployment

---

## Eclipse IDE

### Useful Shortcuts
- Global search: Ctrl+Shift+F
- Quick search: Ctrl+H

---

## Git Commands

### Basic Operations
- Status: `git status`
- Add all: `git add .`
- Commit: `git commit -m "message"`
- Push: `git push origin main`

---

## AWS Services

### Common Services Used
- (Add your AWS services and configurations here)

---

## Troubleshooting

### Docker Issues
- Check running containers: `docker ps`
- View logs: `docker logs container_name`
- Restart container: `docker restart container_name`

### Database Connection Issues
- Always check environment variables first: `env | grep -i postgres`
- Use correct username (not always 'postgres')
- PostgreSQL commands use `\` not `/`

---

## Quick Reference

### Ports in Use
- 5000: Tour Generator Service
- 5001: Tour Processor Service  
- 5433: PostgreSQL (mapped to 5432 inside container)
- 8000+: Local web servers

### File Extensions
- `.md` - Markdown files
- `.py` - Python scripts
- `.txt` - Tour text files
- `.zip` - Netlify deployment packages

---

## API Keys & Credentials

### OpenAI
- API Key: (Add your OpenAI API key here)
- Organization ID: (Add if applicable)

### AWS
- Access Key ID: (Add your AWS access key)
- Secret Access Key: (Add your AWS secret key)
- Region: (Add your default region)

### Other Services
- Netlify: (Add deployment tokens)
- GitHub: (Add personal access tokens)
- Database URLs: (Add connection strings)

---

## Server Configurations

### Nginx
- Config location: `/etc/nginx/nginx.conf`
- Sites available: `/etc/nginx/sites-available/`
- Restart: `sudo systemctl restart nginx`

### Apache
- Config location: `/etc/apache2/apache2.conf`
- Sites available: `/etc/apache2/sites-available/`
- Restart: `sudo systemctl restart apache2`

### Local Development Servers
- Python: `python -m http.server 8000`
- Node.js: `npx serve` or `npm start`
- PHP: `php -S localhost:8000`

---

## Database Schemas

### AudioTours Database
- **tours** table: id, name, location, description, created_at
- **stops** table: id, tour_id, title, content, audio_file, order_num
- **users** table: id, username, email, created_at

### Common Data Types
- Primary keys: `SERIAL PRIMARY KEY` (PostgreSQL)
- Timestamps: `TIMESTAMP DEFAULT CURRENT_TIMESTAMP`
- Text fields: `TEXT` or `VARCHAR(255)`

### the PostgreSQL commands to show the database schema in your Docker container:

#### To list all tables:
```
\dt
```

#### To show schema of a specific table:
```
\d table_name
```

#### To show all tables with more details:
```
\dt+
```

#### To show all schemas:
```
\dn
```

#### To show all tables across all schemas:
```
\dt *.*
```

#### To get complete database schema with SQL:
```sql
SELECT table_name, column_name, data_type 
FROM information_schema.columns
WHERE table_schema = 'public'
ORDER BY table_name, ordinal_position;
```

#### Connection steps:
1. Open Docker Desktop
2. Go to the container "development-postgres-2-1"
3. Click the Exec tab
4. Run: `psql -U admin -d audiotours`
5. Enter your password: `password123`
6. Run any of the schema commands above

*Remember that meta-commands starting with `\` don't need semicolons, but SQL queries do.*

## Common Error Solutions

### Docker Issues
- **Port already in use**: `docker ps` then `docker stop container_name`
- **Permission denied**: Run Docker Desktop as administrator
- **Container won't start**: Check logs with `docker logs container_name`

### Python Issues
- **Module not found**: Check virtual environment is activated
- **Permission denied**: Use `pip install --user package_name`
- **SSL certificate errors**: `pip install --trusted-host pypi.org package_name`

### Database Issues
- **Connection refused**: Check if service is running
- **Authentication failed**: Verify username/password
- **Database doesn't exist**: Create with `CREATE DATABASE db_name;`
- **SQL command produces no output**: Check if you forgot the semicolon (;) at the end
- **Command seems ignored**: All SQL statements MUST end with semicolon

---

## Environment Variables

### .env File Template
```
# Database
DATABASE_URL=postgresql://admin:password123@localhost:5433/audiotours
POSTGRES_USER=admin
POSTGRES_PASSWORD=password123
POSTGRES_DB=audiotours

# API Keys
OPENAI_API_KEY=your_openai_key_here
AWS_ACCESS_KEY_ID=your_aws_key_here
AWS_SECRET_ACCESS_KEY=your_aws_secret_here

# Services
TOUR_GENERATOR_URL=http://localhost:5000
TOUR_PROCESSOR_URL=http://localhost:5001

# Development
DEBUG=True
ENVIRONMENT=development
```

### Loading Environment Variables
- Python: `from dotenv import load_dotenv; load_dotenv()`
- Node.js: `require('dotenv').config()`

---

## Deployment Commands

### Netlify
- Install CLI: `npm install -g netlify-cli`
- Login: `netlify login`
- Deploy: `netlify deploy --prod --dir=build`
- Manual deploy: Drag folder to netlify.com

### AWS
- Install CLI: `pip install awscli`
- Configure: `aws configure`
- S3 sync: `aws s3 sync ./build s3://bucket-name`
- Lambda deploy: `aws lambda update-function-code`

### Docker
- Build: `docker build -t app-name .`
- Run: `docker run -p 8000:8000 app-name`
- Push: `docker push username/app-name`

---

## Testing Commands

### Python Testing
- Run all tests: `python -m pytest`
- Run specific test: `python -m pytest test_file.py`
- With coverage: `python -m pytest --cov=src`
- Verbose output: `python -m pytest -v`

### Node.js Testing
- Run tests: `npm test`
- Watch mode: `npm run test:watch`
- Coverage: `npm run test:coverage`

### Manual Testing
- API testing: Use Postman or `curl`
- Load testing: Use Apache Bench `ab -n 100 -c 10 http://localhost:8000/`

---

## Audio Processing

### FFmpeg Commands
- Convert to MP3: `ffmpeg -i input.wav output.mp3`
- Reduce file size: `ffmpeg -i input.mp3 -b:a 128k output.mp3`
- Trim audio: `ffmpeg -i input.mp3 -ss 00:00:30 -t 00:01:00 output.mp3`
- Combine files: `ffmpeg -f concat -i filelist.txt -c copy output.mp3`

### Audio Formats
- **MP3**: Good compression, widely supported
- **WAV**: Uncompressed, high quality
- **OGG**: Open source, good compression
- **M4A**: Apple format, good quality

### Text-to-Speech
- OpenAI: `openai.Audio.create()`
- Google Cloud: `gcloud ml speech synthesize-text`
- Amazon Polly: `aws polly synthesize-speech`

---

## File Paths

### Important Directories
- **Project root**: `C:\Users\micha\eclipse-workspace\AudioTours\`
- **Development files**: `C:\Users\micha\eclipse-workspace\AudioTours\development\`
- **Audio output**: `C:\Users\micha\eclipse-workspace\AudioTours\audio\`
- **Netlify builds**: `C:\Users\micha\eclipse-workspace\AudioTours\netlify\`

### System Paths
- **Python**: `C:\Python39\python.exe`
- **Node.js**: `C:\Program Files\nodejs\node.exe`
- **Docker**: `C:\Program Files\Docker\Docker\Docker Desktop.exe`

### Configuration Files
- **Requirements**: `requirements.txt`
- **Package.json**: `package.json`
- **Docker**: `Dockerfile`, `docker-compose.yml`
- **Environment**: `.env`, `.env.local`

---

## Network/Firewall

### Port Configurations
- **HTTP**: 80 (production), 8000-8999 (development)
- **HTTPS**: 443 (production)
- **PostgreSQL**: 5432 (default), 5433 (Docker mapped)
- **MongoDB**: 27017
- **Redis**: 6379
- **SSH**: 22

### Windows Firewall
- Open port: `netsh advfirewall firewall add rule name="Port 8000" dir=in action=allow protocol=TCP localport=8000`
- Check open ports: `netstat -an | findstr :8000`
- Kill process on port: `taskkill /PID process_id /F`

### Security Best Practices
- Use HTTPS in production
- Keep API keys in environment variables
- Regular security updates
- Use strong passwords
- Enable 2FA where possible

---
# To reproduce v193 behavior later
git checkout v1.0.0.193
docker-compose up --build
```

**Option 2: Service Version Headers**
Add version tracking to each service:
```python
VERSION = "1.0.0.193"  # Match mobile version
```

## Immediate Action Needed

Let me commit the current service changes and tag them to match v193:

```bash
git add single_file_app_builder.py build_web_page_fixed.py
git commit -m "v193 - Add JavaScript navigation functions for voice commands"
git tag "v1.0.0.193"
git push origin master --tags
```

**Answer:** Currently **NO** - but easily fixable. Should I implement the tagging system now?

---

Please implement, bit so we know when we started please make version 1.1.0.1 and write/add what needs to be remembered so we follow this practice into remind_ai.md.

---

I'll implement the version synchronization system starting with v1.1.0.1 and document the process.

## Step 1: Update Mobile App to v1.1.0.1

---

Starting new versioning system with v1.1.0.1

---

Adding version tracking to tour generation service

---

## Step 2: Add Version Tracking to Services

---

Adding version to health check endpoint

---

Adding comprehensive version management documentation to remind_ai.md

---

## Step 3: Update remind_ai.md with Version Management Process

---

Committing service changes for version synchronization

---

## Step 4: Commit and Tag v1.1.0.1





---

```shell
git add single_file_app_builder.py build_web_page_fixed.py tour_generation_service.py remind_ai.md audio_tour_app/pubspec.yaml

warning: in the working copy of 'build_web_page_fixed.py', LF will be replaced by CRLF the next time Git touches it

warning: in the working copy of 'single_file_app_builder.py', LF will be replaced by CRLF the next time Git touches it

warning: in the working copy of 'tour_generation_service.py', LF will be replaced by CRLF the next time Git touches it

warning: in the working copy of 'remind_ai.md', LF will be replaced by CRLF the next time Git touches it

```

---

Committing and tagging v1.1.0.1 with version synchronization system

---

```shell
git commit -m "v1.1.0.1 - Implement version synchronization system with JavaScript navigation functions" && git tag "v1.1.0.1" && git push origin master --tags

[master 4bac198] v1.1.0.1 - Implement version synchronization system with JavaScript navigation functions
 5 files changed, 265 insertions(+), 6 deletions(-)
 create mode 100644 remind_ai.md

To https://github.com/michaelglik-audiotoursai/Audio-Tours.git
   1726c25..4bac198  master -> master
 * [new tag]         v1.1.0.1 -> v1.1.0.1

```

---

## Step 5: Deploy Services with Version Tracking





---

Deploying versioned services to containers

---

```shell
docker cp tour_generation_service.py development-tour-processor-1:/app/tour_generation_service.py && docker cp single_file_app_builder.py development-tour-processor-1:/app/single_file_app_builder.py && docker cp build_web_page_fixed.py development-tour-processor-1:/app/build_web_page_fixed.py

```

---

Restarting container with v1.1.0.1 services

---

```shell
docker restart development-tour-processor-1

development-tour-processor-1

```

---



## ✅ Version Synchronization System Implemented!

### **What's Now in Place:**

**🏷️ Version v1.1.0.1 Tagged:**
- Mobile app: `version: 1.1.0+1`
- Services: `SERVICE_VERSION = "1.1.0.1"`
- Git tag: `v1.1.0.1` 
- GitHub will build APK v1.1.0.1

**📋 Process Documented in remind_ai.md:**
- Step-by-step version management workflow
- Commands for reproducing any version
- Requirements for mobile-service alignment

**🔄 Reproducibility Achieved:**
```bash
# To reproduce v1.1.0.1 behavior anytime:
git checkout v1.1.0.1
docker-compose up --build
# + Install APK v1.1.0.1 from GitHub releases
```

**🎯 Next Version Process:**
1. Increment to v1.1.0.2 in pubspec.yaml
2. Update SERVICE_VERSION in modified files
3. Commit with tag: `git tag "v1.1.0.2"`
4. Deploy services

**Now you can reproduce any version's complete behavior - mobile + services!**

## Version Management Workflow Tutorial

Now let me show you how to use the version management system:

### 1. **Commit Current State (1.1.0+1)**
```cmd
version_management.bat commit 1.1.0+1
```
This saves current state as baseline.

### 2. **Deploy Voice Fix (1.1.0+2)**  
```cmd
version_management.bat commit 1.1.0+2
version_management.bat deploy 1.1.0+2
```
This creates the fix and deploys it.

### 3. **Rollback Example (back to 1.1.0+1)**
```cmd
version_management.bat rollback 1.1.0+1
```
This reverts services and tells you to download old APK.

### 4. **Forward to Latest (1.1.0+2)**
```cmd
version_management.bat deploy 1.1.0+2
```
## Windows Commands

### Directory Listing with Filters
- List directories only: `dir /ad`
- Sort by creation time: `dir /tc`
- List directories created today: `dir /ad /tc | find "07/14/2025"`
- PowerShell alternative: `Get-ChildItem -Directory | Where-Object {$_.CreationTime -gt (Get-Date).Date.AddHours(22).AddMinutes(30)}`

-----
*Last updated: 2025/08/11/ 11:54*
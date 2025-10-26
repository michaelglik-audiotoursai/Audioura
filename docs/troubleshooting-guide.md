# Troubleshooting Guide

## Android Build Issues

### ClassNotFoundException
**Symptoms**: App crashes immediately, "keeps stopping" message
**Check**: Package name alignment
- AndroidManifest.xml: `com.audiotours.dev.MainActivity`
- build.gradle.kts: `applicationId = "com.audiotours.dev"`
- MainActivity.kt: Must be in `com.audiotours.dev` package

**Fix**: Move MainActivity.kt to correct package and directory structure

### Windows Build Failures
**Symptoms**: Flutter build fails locally on Windows
**Solution**: Use GitHub Actions for reliable Linux-based builds
**Process**: Push code changes, let GitHub build APK automatically

### APK Testing Process
1. Install: `flutter install --use-application-binary="path/to/apk"`
2. Check logs: `adb logcat -d *:E` (from platform-tools directory)
3. Look for: ClassNotFoundException, package mismatches, missing dependencies

## Service Issues

### Container Connection Problems
**Check containers**: `docker ps`
**Check logs**: `docker logs container-name`
**Check network**: `docker network ls`

### Database Connection Issues
**Test connection**: 
```bash
docker exec -t development-postgres-2-1 pg_dump -U admin audiotours > test.sql
```
**Backup before changes**: Always create backup before modifications

### Service Deployment Issues
**Verify file copy**: Check file exists in container after `docker cp`
**Restart required**: Always `docker restart container-name` after file changes
**Version mismatch**: Ensure service version matches mobile app version

## GitHub Actions Issues

### Build Not Triggering
**Check**: Version increment in `pubspec.yaml`
**Check**: Git push to master branch
**Check**: GitHub Actions tab for build status

### Build Failures
**Check**: GitHub Actions logs for specific errors
**Common**: Dependency conflicts, missing files, syntax errors
**Solution**: Fix locally, increment version, push again

## Data Recovery

### Lost Container Data
**Prevention**: Use named volumes, avoid `docker-compose down -v`
**Recovery**: Restore from database backup
**Process**: `docker exec -i container-name psql -U admin audiotours < backup.sql`

### Version Rollback
```bash
git checkout v[PREVIOUS_VERSION]
docker-compose down
docker-compose up --build
```
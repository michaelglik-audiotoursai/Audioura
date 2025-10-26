# Important Directive for Development

**Directive: Always modify files ONLY in the local directory at c:\Users\micha\eclipse-workspace\AudioTours\development\ first, then copy these modified files to the Docker containers. Never modify files directly in the containers.**

## Workflow

1. Make all changes to files in the local directory
2. After changes are complete, copy the modified files to the Docker containers
3. This ensures the local directory is always the source of truth

## Implementation

When making changes:
1. First create a backup of the local file
2. Modify the local file
3. Copy the modified local file to the container
4. Restart the relevant service

This approach ensures that the local directory always contains the most up-to-date versions of all files, and the containers simply receive copies of these files.
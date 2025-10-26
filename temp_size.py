import os

with open("temp_files_input.txt", 'r') as f:
    files = f.read().split('\n')

sum = 0
for file in files:
    if len(file) == 0:
        continue
    sum += os.path.getsize(file)

print(f'Total size: {sum}')

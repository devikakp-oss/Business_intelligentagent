for line in open('app.py'):
    if '\t' in line:
        print(repr(line))
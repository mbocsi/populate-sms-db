# Steam Market Stats DB
Populates the MySQL database with items from the steam market using Prisma Client.

## Usage
```
pip install -r requirements.txt
prisma db pull
prisma generate
python main.py
```
### Required Environment Variables
```
DATABASE_URL=<Database URL>
```
Place inside a .env file at root project directory.
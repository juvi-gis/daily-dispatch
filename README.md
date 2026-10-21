# Daily Dispatch

A Django news website. Journalists write articles, editors approve them, and
readers get approved articles by email from the journalists and publishers
they follow. It also has a REST API. The database is **MariaDB**.

## Setup

### Windows quick start (Command Prompt + MariaDB)

These instructions are for **Command Prompt** (`cmd.exe`), not PowerShell.
Install Git, Python 3.10 or newer, and MariaDB first. Make sure the MariaDB
server is running. Copy and paste this first block:

```bat
git clone https://github.com/juvi-gis/daily-dispatch.git
cd daily-dispatch
py -m venv venv
venv\Scripts\activate.bat
python -m pip install -r requirements.txt
```

Create the database. This command prompts for your MariaDB root password:

```bat
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS news_db CHARACTER SET utf8mb4;"
```

If `mysql` is not recognised, run `mariadb.exe` from your MariaDB `bin`
folder instead. For example, use its full path in place of `mysql`.

Back in the same Command Prompt window, set the password Django should use.
Replace the example value with your MariaDB root password; do not include
angle brackets:

```bat
set "DB_PASSWORD=your-mariadb-root-password"
```

Then create the Django tables and admin login, and start the app:

```bat
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open **http://127.0.0.1:8000/** in your browser. The admin site is at
**http://127.0.0.1:8000/admin/**. Keep this Command Prompt window open while
using the app; press **Ctrl+C** to stop the server. The `DB_PASSWORD` setting
only lasts for this Command Prompt window, so set it again in a new one.

## Try it out

1. At `/register/`, sign up an **Editor**, a **Reader** (use an email
   address) and two **Journalists**. You are logged in straight after
   signing up, so log out between users. Each email address can only be used
   once.
2. As the editor, open **Publishers**, click **New publisher**, and tick one
   journalist (and any other editors) to assign them. That journalist now
   works for a publishing house. The other journalist is independent.
3. As the reader, open **My subscriptions** and tick both journalists.
4. As the independent journalist, click **Write article**. The publisher
   choice is "Independent", so the article is saved as a **draft**. Open
   **My articles** and click **Publish**. The reader is emailed.
5. As the publishing-house journalist, click **Write article** and choose
   the publisher. The article is **pending** and has no Publish button,
   because only an editor can approve it. You can still edit or delete it
   from **My articles**.
6. As the editor, open **Review queue** and approve it. The reader is
   emailed.
7. As a journalist, create a newsletter. Only published articles are listed.

The emails appear in the terminal where the server is running, and each
published article adds an entry in the admin under **Approved article
logs**.

## Run the tests

```
python manage.py test newsroom
```

## Roles

| Role | Can do |
|---|---|
| Reader | View articles and newsletters, follow publishers and journalists |
| Journalist | Write, edit and delete their own articles and newsletters. Publish their own independent articles. See their drafts and pending articles under My articles |
| Editor | Review and approve publisher articles, edit or delete any article or newsletter, create publishers and assign editors and journalists |

All three roles can sign up at `/register/`.

## REST API

Get a token at `/api/token/` (POST your username and password), then send
`Authorization: Token <your-token>` with each request.

| Method | Address | Who |
|---|---|---|
| GET | `/api/articles/` | Everyone (approved articles) |
| GET | `/api/articles/subscribed/` | Readers (only what they follow) |
| GET | `/api/articles/<id>/` | Everyone |
| POST | `/api/articles/` | Journalists |
| PUT / DELETE | `/api/articles/<id>/` | Editors, or the journalist who wrote it |
| POST | `/api/articles/<id>/approve/` | Editors (publisher articles only) |
| POST | `/api/articles/<id>/publish/` | The journalist who wrote it (independent articles only) |

## More information

- Requirements, diagrams and database design: `docs/dailydispatch_design.md` and
  `docs/dailydispatch_design.drawio`
- Approval uses Django signals: when an article is first approved, its
  subscribers are emailed and it is logged at `/api/approved/`.

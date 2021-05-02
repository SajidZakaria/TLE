# TLE (+ Heroku)

This repository helps to run tle directly in the heroku. For more information about TLE, check the [main repository](https://github.com/cheran-senthil/TLE).

---

## Steps for hosting a bot for your own server using Heroku.

1. Download the heroku CLI from [here](https://devcenter.heroku.com/articles/heroku-cli)
2. Now after installing the CLI, open up the CLI if you are on windows or open up a terminal if you are on linux.
3. Now enter the command `heroku login` and it will open up a link in the browser for login. Login using your credentials.
4. Now clone this repository from the terminal using the command `git clone https://github.com/ParsaAlizadeh/TLE.git`.
5. After cloning move into the TLE directory using `cd TLE`. Then checkout on hoi branch using `git checkout hoi`
6. Now enter `heroku create` command in the terminal and hit enter. It will create a new app for you. Remember the name.
7. Now you need to add two buildpacks to deploy. The APT buildpack to install essential APT files and Python buildpack to install essential packages.
8. To add APT buildpack type the following command `heroku buildpacks:add heroku-community/apt`.
9. To add Python buldpack type the following command `heroku buildpacks:add heroku/python`.
    > **Note**: the order of adding the buildpacks is important.
10. Now go to the personal dashboard [page](https://dashboard.heroku.com/apps) of heroku on your browser.
11. Next click on the app you created in step 6.
12. Now, go to resources and click on **Find more add-ons** and find **Heroku Postgres**. 
13. Click to install the database on the Hobby Dev plan and set the app to the one that hosts the bot.
14. Go to settings tab and you will see a section called **Config Vars**. Click on the **reveal config vars** button.
15. Now you need to create a config var called `BOT_TOKEN` and paste your bot token created using discord and hit add.
16. Make sure that the name of the config var that contains the database url is named `DATABASE_URL`.  
17. Now you are almost done. Type the following command `git push heroku hoi:master -f` and press enter.
18. It will take few minutes to build and deploy
19. After successful build open the heroku app in your browser. The same step as 10.
20. Go to Resources tab and turn on the worker. You are not charged for doing this its completely free.
21. That's it Enjoy!

## Troubleshoot

### Error R14 (Memory quota exceeded)

Error R14 doesn't stop dynos. According to [this heroku article](https://devcenter.heroku.com/articles/error-codes#r14-memory-quota-exceeded),
if this error occurs, the dyno will page to swap space to continue running, which may cause degraded process performance.

### psycopg2.errors.InFailedSqlTransaction

By using `;meta rollback` or `;meta reconnect`, the error should be fixed and other commands will run normally.

This error causes from [user database](tle/util/db/user_db_conn.py). Feel free to pull request if you can fix this.

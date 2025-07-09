# MongoDB Atlas Setup Guide for V-Lab Backend

## Overview
This guide will help you set up MongoDB Atlas (cloud MongoDB) for your V-Lab backend application.

## Step 1: Create MongoDB Atlas Account

1. Go to [MongoDB Atlas](https://cloud.mongodb.com/)
2. Click "Start Free" or "Sign In" if you have an account
3. Create a new account or log in with existing credentials

## Step 2: Create a New Cluster

1. After logging in, click "Create" and then "Cluster"
2. Choose the **FREE** tier (M0 Sandbox)
3. Select a cloud provider and region (choose one closest to you)
4. Give your cluster a name (e.g., "v-lab-cluster")
5. Click "Create Cluster" (this may take a few minutes)

## Step 3: Configure Database Access

### Create Database User
1. Go to "Database Access" in the left sidebar
2. Click "Add New Database User"
3. Choose "Password" authentication
4. Enter a username and strong password
5. Set user privileges to "Read and write to any database"
6. Click "Add User"

### Configure Network Access
1. Go to "Network Access" in the left sidebar
2. Click "Add IP Address"
3. For development, you can click "Allow Access from Anywhere" (0.0.0.0/0)
   - **Note:** For production, use specific IP addresses
4. Click "Confirm"

## Step 4: Get Connection String

1. Go to "Clusters" in the left sidebar
2. Click "Connect" on your cluster
3. Choose "Connect your application"
4. Select "Python" and version "3.6 or later"
5. Copy the connection string (it looks like this):
   ```
   mongodb+srv://username:password@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
   ```

## Step 5: Update Your .env File

1. Open your `.env` file in the project root
2. Update the MongoDB configuration:
   ```
   MONGODB_URL=mongodb+srv://YOUR_USERNAME:YOUR_PASSWORD@YOUR_CLUSTER.mongodb.net/vlabdb?retryWrites=true&w=majority
   DATABASE_NAME=vlabdb
   ```
3. Replace:
   - `YOUR_USERNAME` with your database username
   - `YOUR_PASSWORD` with your database password
   - `YOUR_CLUSTER` with your actual cluster name

## Step 6: Test the Connection

Run the MongoDB test script:
```bash
python test_mongodb_setup.py
```

This script will:
- Test the connection to MongoDB Atlas
- Create necessary database indexes
- Verify that read/write operations work

## Step 7: Start Your Backend

Once the connection test passes, you can start your backend:
```bash
python -m src.main
```

## Database Collections

Your application will automatically create these collections:
- **users**: User accounts and authentication data
- **circuits**: Saved circuit designs and netlists
- **simulations**: Simulation history and results

## Security Best Practices

### For Production:
1. **IP Whitelist**: Only allow specific IP addresses, not 0.0.0.0/0
2. **Strong Passwords**: Use complex passwords for database users
3. **Environment Variables**: Keep credentials in environment variables, never in code
4. **SSL/TLS**: MongoDB Atlas uses SSL/TLS by default
5. **Regular Backups**: MongoDB Atlas provides automatic backups

### Connection String Security:
- Never commit your connection string to version control
- Use environment variables for all sensitive data
- Rotate database passwords regularly

## Troubleshooting

### Common Issues:

1. **Connection Timeout**
   - Check your IP whitelist in Network Access
   - Verify your internet connection

2. **Authentication Failed**
   - Double-check username and password in connection string
   - Ensure the database user has proper permissions

3. **DNS Resolution Error**
   - Install dnspython: `pip install dnspython`
   - Check if your network blocks MongoDB Atlas ports

4. **SSL Certificate Error**
   - Update your system's SSL certificates
   - Try adding `&ssl_cert_reqs=CERT_NONE` to connection string (development only)

### Getting Help:
- MongoDB Atlas documentation: https://docs.atlas.mongodb.com/
- MongoDB University (free courses): https://university.mongodb.com/
- Community forums: https://community.mongodb.com/

## Testing Your Setup

Use the provided test files to verify everything works:

1. **Database Connection**: `python test_mongodb_setup.py`
2. **Authentication**: Use the endpoints in `test_simulation.http`
3. **Simulation**: Run authenticated simulation tests

Your V-Lab backend is now ready to use MongoDB Atlas for user management, circuit storage, and simulation history!

/**
 * youtube_auth_setup.js — Standalone Node.js OAuth 2.0 helper for YouTube API
 */
const http = require('http');
const { exec } = require('child_process');
const fs = require('fs');
const path = require('path');
const readline = require('readline');

const SCOPES = [
  'https://www.googleapis.com/auth/youtube.upload',
  'https://www.googleapis.com/auth/youtube',
  'https://www.googleapis.com/auth/youtube.force-ssl'
];

async function ask(query) {
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });
  return new Promise((resolve) => rl.question(query, (ans) => {
    rl.close();
    resolve(ans.trim());
  }));
}

async function main() {
  console.log('='.repeat(70));
  console.log('   YouTube Channel OAuth 2.0 Setup (One-Time Token Generator)');
  console.log('='.repeat(70));

  let clientId = process.argv[2] || process.env.YOUTUBE_CLIENT_ID;
  let clientSecret = process.argv[3] || process.env.YOUTUBE_CLIENT_SECRET;

  const clientSecretsPath = path.join(__dirname, 'client_secrets.json');
  if (fs.existsSync(clientSecretsPath)) {
    try {
      const data = JSON.parse(fs.readFileSync(clientSecretsPath, 'utf8'));
      const info = data.installed || data.web || {};
      clientId = clientId || info.client_id;
      clientSecret = clientSecret || info.client_secret;
    } catch (e) {}
  }

  if (!clientId) {
    clientId = await ask('\nEnter your Google OAuth Client ID: ');
  }
  if (!clientSecret) {
    clientSecret = await ask('Enter your Google OAuth Client Secret: ');
  }

  if (!clientId || !clientSecret) {
    console.error('❌ Client ID and Secret are required.');
    process.exit(1);
  }

  const port = 8080;
  const redirectUri = `http://localhost:${port}/`;

  // Direct code exchange fallback
  const codeArgIdx = process.argv.findIndex(a => a === '--code');
  let manualCode = codeArgIdx !== -1 ? process.argv[codeArgIdx + 1] : null;
  if (manualCode) {
    if (manualCode.includes('code=')) {
      try {
        const u = new URL(manualCode);
        manualCode = u.searchParams.get('code');
      } catch (e) {
        const match = manualCode.match(/code=([^&]+)/);
        if (match) manualCode = decodeURIComponent(match[1]);
      }
    }
    console.log('\n⏳ Exchanging provided authorization code for tokens...');
    const tokenRes = await fetch('https://oauth2.googleapis.com/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({
        code: manualCode,
        client_id: clientId,
        client_secret: clientSecret,
        redirect_uri: redirectUri,
        grant_type: 'authorization_code'
      }).toString()
    });
    const tokenData = await tokenRes.json();
    if (!tokenRes.ok || tokenData.error) {
      console.error('❌ Failed to obtain tokens:', tokenData);
      process.exit(1);
    }
    const refreshToken = tokenData.refresh_token;
    if (!refreshToken) {
      console.warn('⚠️ No refresh token was returned.');
      process.exit(1);
    }
    console.log('🎉 OAuth Authorization Complete!');
    console.log(`\nYOUTUBE_REFRESH_TOKEN=${refreshToken}`);
    // Sync to .env and gh
    const envPath = path.join(__dirname, '.env');
    let envContent = fs.existsSync(envPath) ? fs.readFileSync(envPath, 'utf8') : '';
    const setEnvVar = (content, key, val) => {
      const regex = new RegExp(`^${key}=.*$`, 'm');
      if (regex.test(content)) return content.replace(regex, `${key}=${val}`);
      return content + (content.endsWith('\n') || !content ? '' : '\n') + `${key}=${val}\n`;
    };
    envContent = setEnvVar(envContent, 'YOUTUBE_CLIENT_ID', clientId);
    envContent = setEnvVar(envContent, 'YOUTUBE_CLIENT_SECRET', clientSecret);
    envContent = setEnvVar(envContent, 'YOUTUBE_REFRESH_TOKEN', refreshToken);
    fs.writeFileSync(envPath, envContent, 'utf8');
    const ghBin = fs.existsSync('C:\\Program Files\\GitHub CLI\\gh.exe')
      ? '"C:\\Program Files\\GitHub CLI\\gh.exe"'
      : 'gh';
    exec(`${ghBin} secret set YOUTUBE_CLIENT_ID --body "${clientId}"`, () => {
      exec(`${ghBin} secret set YOUTUBE_CLIENT_SECRET --body "${clientSecret}"`, () => {
        exec(`${ghBin} secret set YOUTUBE_REFRESH_TOKEN --body "${refreshToken}"`, () => {
          console.log('✅ Updated all GitHub Secrets!');
          process.exit(0);
        });
      });
    });
    return;
  }

  const authUrl = `https://accounts.google.com/o/oauth2/v2/auth?client_id=${encodeURIComponent(
    clientId
  )}&redirect_uri=${encodeURIComponent(redirectUri)}&response_type=code&scope=${encodeURIComponent(
    SCOPES.join(' ')
  )}&access_type=offline&prompt=consent`;

  const server = http.createServer(async (req, res) => {
    try {
      const reqUrl = new URL(req.url, `http://localhost:${port}`);
      const code = reqUrl.searchParams.get('code');
      const error = reqUrl.searchParams.get('error');

      if (error) {
        res.writeHead(400, { 'Content-Type': 'text/html' });
        res.end(`<h2>Authorization Error: ${error}</h2>`);
        console.error(`\n❌ Authorization failed: ${error}`);
        server.close();
        process.exit(1);
      }

      if (!code) {
        res.writeHead(404);
        res.end();
        return;
      }

      res.writeHead(200, { 'Content-Type': 'text/html' });
      res.end(`
        <div style="font-family:sans-serif; text-align:center; padding:50px;">
          <h1 style="color:#16a34a;">🎉 Authorization Successful!</h1>
          <p>You can close this tab and return to the application.</p>
        </div>
      `);

      server.close();

      console.log('\n⏳ Exchanging authorization code for tokens...');
      const tokenRes = await fetch('https://oauth2.googleapis.com/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({
          code: code,
          client_id: clientId,
          client_secret: clientSecret,
          redirect_uri: redirectUri,
          grant_type: 'authorization_code'
        }).toString()
      });

      const tokenData = await tokenRes.json();
      if (!tokenRes.ok || tokenData.error) {
        console.error('❌ Failed to obtain tokens:', tokenData);
        process.exit(1);
      }

      const refreshToken = tokenData.refresh_token;
      if (!refreshToken) {
        console.warn('⚠️ No refresh token was returned.');
        console.warn('Go to https://myaccount.google.com/permissions to revoke access, then run again.');
        process.exit(1);
      }

      console.log('\n' + '='.repeat(70));
      console.log('🎉 OAuth Authorization Complete!');
      console.log('='.repeat(70));
      console.log(`\nYOUTUBE_CLIENT_ID=${clientId}`);
      console.log(`YOUTUBE_CLIENT_SECRET=${clientSecret}`);
      console.log(`YOUTUBE_REFRESH_TOKEN=${refreshToken}`);

      // Save to local .env
      const envPath = path.join(__dirname, '.env');
      let envContent = '';
      if (fs.existsSync(envPath)) {
        envContent = fs.readFileSync(envPath, 'utf8');
      }
      const setEnvVar = (content, key, val) => {
        const regex = new RegExp(`^${key}=.*$`, 'm');
        if (regex.test(content)) {
          return content.replace(regex, `${key}=${val}`);
        }
        return content + (content.endsWith('\n') || !content ? '' : '\n') + `${key}=${val}\n`;
      };
      envContent = setEnvVar(envContent, 'YOUTUBE_CLIENT_ID', clientId);
      envContent = setEnvVar(envContent, 'YOUTUBE_CLIENT_SECRET', clientSecret);
      envContent = setEnvVar(envContent, 'YOUTUBE_REFRESH_TOKEN', refreshToken);
      fs.writeFileSync(envPath, envContent, 'utf8');
      console.log('\n✅ Updated local .env file.');

      // Update GitHub Secrets via GitHub CLI
      console.log('🔄 Syncing secrets to GitHub repository via GitHub CLI...');
      const ghBin = fs.existsSync('C:\\Program Files\\GitHub CLI\\gh.exe')
        ? '"C:\\Program Files\\GitHub CLI\\gh.exe"'
        : 'gh';
      try {
        exec(`${ghBin} secret set YOUTUBE_CLIENT_ID --body "${clientId}"`, () => {
          exec(`${ghBin} secret set YOUTUBE_CLIENT_SECRET --body "${clientSecret}"`, () => {
            exec(`${ghBin} secret set YOUTUBE_REFRESH_TOKEN --body "${refreshToken}"`, (err) => {
              if (!err) {
                console.log('✅ Successfully updated all 3 GitHub Secrets (YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN)!');
              } else {
                console.log('ℹ️ Updated local .env. GitHub CLI secret sync error:', err.message);
              }
              process.exit(0);
            });
          });
        });
      } catch (err) {
        console.error('GitHub secret sync error:', err);
        process.exit(0);
      }

    } catch (err) {
      console.error('Error handling redirect:', err);
      server.close();
      process.exit(1);
    }
  });

  server.listen(port, () => {
    console.log(`\n🌐 Opening browser for authorization...\n`);
    console.log(`If it doesn't open automatically, open this URL:`);
    console.log(`👉 ${authUrl}\n`);
    exec(`start "" "${authUrl}"`);
  });
}

main().catch(console.error);

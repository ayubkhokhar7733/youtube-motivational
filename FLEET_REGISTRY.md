# YouTube Automation Fleet Registry & Uploader Matrix

> **Last Updated**: November 22, 2026  
> **Master Reference**: Complete directory of all channels, owners, repositories, and Google Cloud OAuth Uploader Apps.

---

## 1. Google Cloud OAuth Uploader Apps

| App Name | Purpose / Scope | Client ID | Client Secret | Redirect URI |
| :--- | :--- | :--- | :--- | :--- |
| **Uploader 1 (Original Fleet)** | Primary / Flagship channels | (Stored securely in GitHub Secrets) | (Stored securely in GitHub Secrets) | `http://localhost:8080/` |
| **Uploader 2 (`Youtube-auto`)** | Secondary / High-volume family channels | (Stored securely in GitHub Secrets) | (Stored securely in GitHub Secrets) | `http://localhost:8080/` |

---

## 2. Channel & Member Directory

| Channel Name | Owner | Handle | Primary Speaker | Repository | Uploader App |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Sabiduría Diaria** | Ayub (Main / Flagship) | `@sabiduriadiaria-g6p` | Dra. Nazareth Castellanos | `ayubkhokhar7733/youtube-motivational` | **App 1** |
| **Sabiduría Estoica** | Hasaan Khokhar (Nephew) | `@SabiduriaEstoica-z1n` | Walter Riso | `ayubkhokhar7733/channel-sabiduria-estoica` | **App 2** |
| **Sabiduría Femenina 2026** | Brother | `@SabiduriaFemenina2026` | Nilda Chiaraviglio | `ayubkhokhar7733/channel-sabiduria-femenina` | **App 2** |
| **Mejora Día a Día** | Zahid Khurshid | `@betterdaybyday0` | Dra. Nazareth Castellanos | `ayubkhokhar7733/channel-mejora-dia-a-dia` | **App 1** |
| **El Arte de la Psique 2.0** | Shafqat Chadiyo | `@elartedelapsique2.0` | Carl Jung | `ayubkhokhar7733/channel-el-arte-psique` | **App 1** |
| **Mente Libre** | Jam Irshad | `@mentelibre2027` | Walter Riso | `ayubkhokhar7733/channel-mente-libre` | **App 1** |
| **Mente en Calma** | Zeeshan Mushir | `@MenteEnCalmaofficials` | Dra. Marian Rojas Estapé | `ayubkhokhar7733/channel-mente-en-calma` | **App 1** |
| **Entre Fases e Aprendizados** | Waqar Chandiyo | `@EntreFases-b9x` | Especialistas em Dev Pessoal | `ayubkhokhar7733/channel-entre-fases` | **App 1** |
| **Esencia Femenina oficial** | Family Member | `@mrxEF804` | Nilda Chiaraviglio & Expertas | `ayubkhokhar7733/channel-esencia-femenina` | **App 1** |
| **Amor Propio y Paz** | Rashid Bukhari | `@AmorPropioyPaz-k8u` | Dra. Nazareth Castellanos | `ayubkhokhar7733/channel-amor-propio-paz` | **App 1** |

---

## 3. Instant 30-Second Uploader Switch Procedure

When switching any channel to **Uploader 2**:

1. **Set GitHub Secrets on target repo**:
   ```bash
   gh secret set YOUTUBE_CLIENT_ID --repo <repo> --body "<UPLOADER_2_CLIENT_ID>"
   gh secret set YOUTUBE_CLIENT_SECRET --repo <repo> --body "<UPLOADER_2_CLIENT_SECRET>"
   ```

2. **Generate Direct OAuth URL**:
   ```
   https://accounts.google.com/o/oauth2/v2/auth?client_id=<UPLOADER_CLIENT_ID>&redirect_uri=http%3A%2F%2Flocalhost%3A8080%2F&response_type=code&scope=https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fyoutube.upload+https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fyoutube.force-ssl&access_type=offline&prompt=consent&state=<channel_id>_oauth_state
   ```

3. **Exchange Callback Code & Set Refresh Token**:
   Exchange code via POST to `https://oauth2.googleapis.com/token`, then:
   ```bash
   gh secret set YOUTUBE_REFRESH_TOKEN --repo <repo> --body "<refresh_token>"
   ```

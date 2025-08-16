<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0"
  xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
xmlns:om="https://omrey86.neocities.org/" >

  <xsl:output method="html" encoding="UTF-8" indent="yes"/>

  <xsl:template match="/">
    <html>
      <head>
      	
        <title>
<xsl:if test="/rss/channel/om:autor">
      	<xsl:value-of select="rss/channel/om:autor"/> presenta: </xsl:if><xsl:value-of select="rss/channel/title"/>
</title>

         <meta name="viewport" content="width=device-width, initial-scale=1"/>
        <style type="text/css">
          body {
            font-family: Arial, sans-serif;
            max-width: 600;
            width: 90%;
            background: linear-gradient(
  to bottom,
  <xsl:value-of select="/rss/channel/om:cfb1"/> 0%,
  <xsl:value-of select="/rss/channel/om:cfb2"/> 700px,
  <xsl:value-of select="/rss/channel/om:cfb2"/> 100%
);
            color: <xsl:value-of select="/rss/channel/om:ct"/>;
            padding: 20px;
            font-size: 14px;
            margin: auto;
          }
          
          a {
  color: <xsl:value-of select="/rss/channel/om:clink"/>;
  text-decoration: underline;
  word-break: break-all; /* Rompe enlaces si son muy largos */
}

          h1 {
            color: <xsl:value-of select="/rss/channel/om:ch1"/>;
            border-bottom: 2px solid <xsl:value-of select="/rss/channel/om:ch1"/>;
            padding-bottom: 5px;
            font-size: 3em;
            text-align: center;
          }
          .podcast-image {
            display: block;
            margin-bottom: 20px;
            max-width: 200px;
            height: auto;
            border-radius: 8px;
          }
          .item {
            background: <xsl:value-of select="/rss/channel/om:cfi"/>;
            margin: 15px 0;
            padding: 15px;
            border-radius: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            display: flex;
            align-items: center;
            gap: 15px; /* Espacio entre la imagen y el texto del episodio */
          }
          
.item-description {
  max-width: 100%;
  overflow-wrap: break-word; /* Corta palabras largas como URLs */
  word-wrap: break-word;
  word-break: break-word;
  line-height: 1.6;
}

.item-description a {
  color: <xsl:value-of select="/rss/channel/om:clink"/>;
  text-decoration: underline;
  word-break: break-all; /* Rompe enlaces si son muy largos */
}

.item-description img {
  max-width: 90%;
  height: auto;
  display: block;
  margin: 10px auto; /* ¡Centrado! */
  border-radius: 4px;
}

          .item-content {
            flex-grow: 1;
          }
          
  .item img {
    display: block;
    margin: 10px auto;
    max-width: 100%;
    height: auto;
  }

          .item-title {
            font-size: 2em;
            font-weight: bold;
            color: <xsl:value-of select="/rss/channel/om:cti"/>;
            margin-bottom: 5px;
          }
          .item-date {
            font-size: 0.9em;
            color: #888;
            margin-bottom: 10px;
          }
          .episode-image {
            max-width: 100px; /* Tamaño de la imagen del episodio */
            height: auto;
            border-radius: 4px;
          }
          .listen-link {
            display: inline-block;
            margin-top: 10px;
            padding: 20px 28px;
            background-color: #28a745;
            color: white;
            text-decoration: none;
            border-radius: 30px;
          }
          .listen-link:hover {
            background-color: #218838;
          }
          

          
          
          .subscribe-buttons {
  margin-top: 20px;
  display: flex;
  justify-content: center;
  gap: 10px;
}

.subscribe-button {
  width: 40px;
  height: 40px;
  display: inline-block;
  border-radius: 6px;
  overflow: hidden;
  background-color: transparent;
}

.subscribe-button img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
  details summary .resumen {
    display: inline;
  }

  details[open] summary .resumen {
    display: none;
  }
        
          #scrollTopBtn {
            display: none;
            position: fixed;
            bottom: 30px;
            right: 30px;
            z-index: 100;
            font-size: 24px;
            background-color: #444;
            color: white;
            border: none;
            border-radius: 50%;
            padding: 12px 16px;
            cursor: pointer;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
          }

          #scrollTopBtn:hover {
            background-color: #222;
          }
</style>
      </head>
      <body>
      	<xsl:if test="normalize-space(/rss/channel/om:autor) != ''"> 
      	<p>
      	<xsl:value-of select="rss/channel/om:autor"/> presenta:
      </p>
      </xsl:if> 
      
        <h1>
          <xsl:value-of select="rss/channel/title"/>
        </h1>


<div style="text-align: center;">
  <img src="{rss/channel/image/url}" 
     alt="{rss/channel/image/title}"
Width="70%"/>
<xsl:if test="rss/channel/om:suscripciones/*[normalize-space(.) != '']">
  <p>Suscríbete en:</p>
  	<div class="subscribe-buttons">
<!-- iVoox -->
<xsl:if test="normalize-space(/rss/channel/om:suscripciones/om:ivoox) != ''"> 
  <a class="subscribe-button" href="{/rss/channel/om:suscripciones/om:ivoox}">
    <img src="../img/ivoox.png" alt="iVoox" />
  </a>
</xsl:if>

<!-- Apple Podcasts -->
<xsl:if test="normalize-space(/rss/channel/om:suscripciones/om:apple) != ''">
  <a class="subscribe-button" href="{/rss/channel/om:suscripciones/om:apple}">
    <img src="../img/apple.jpg" alt="Apple Podcasts" />
  </a>
</xsl:if>

<!-- Podcasts Index -->
<xsl:if test="normalize-space(/rss/channel/om:suscripciones/om:index) != ''">
  <a class="subscribe-button" href="{/rss/channel/om:suscripciones/om:index}">
    <img src="../img/index.jpg" alt="Podcasts Index" />
  </a>
</xsl:if>

<!-- Spotify -->
<xsl:if test="normalize-space(/rss/channel/om:suscripciones/om:spotify) != ''">
  <a class="subscribe-button" href="{/rss/channel/om:suscripciones/om:spotify}">
    <img src="../img/spotify.png" alt="Spotify" />
  </a>
</xsl:if>

<!-- YouTube -->
<xsl:if test="normalize-space(/rss/channel/om:suscripciones/om:youtube) != ''">
  <a class="subscribe-button" href="{/rss/channel/om:suscripciones/om:youtube}">
    <img src="../img/youtube.png" alt="YouTube" />
  </a>
</xsl:if>

<!-- Pocket Casts -->
<xsl:if test="normalize-space(/rss/channel/om:suscripciones/om:pocketcasts) != ''">
  <a class="subscribe-button" href="{/rss/channel/om:suscripciones/om:pocketcasts}">
    <img src="../img/pocketcast.png" alt="Pocket Casts" />
  </a>
</xsl:if>

<!-- Amazon Music -->
<xsl:if test="normalize-space(/rss/channel/om:suscripciones/om:amazon) != ''">
  <a class="subscribe-button" href="{/rss/channel/om:suscripciones/om:amazon}">
    <img src="../img/amazonmusic.png" alt="Amazon Music" />
  </a>
</xsl:if>

<!-- OPML -->
<xsl:if test="normalize-space(/rss/channel/om:suscripciones/om:opml) != ''">
  <a class="subscribe-button" href="{/rss/channel/om:suscripciones/om:opml}" download="Abrir con app de Podcast.opml">
    <img src="../img/opml.png" alt="OPML" />
  </a>
</xsl:if>
</div> 
</xsl:if>
</div>

  <p>
        <br/>Busca "<span style="color: {/rss/channel/om:ch1}; font-weight: bold;"><xsl:value-of select="rss/channel/title"/></span>" en tu aplicación de podcast preferida.
  </p>
  
  <div style="text-align: center;">
<p> Métodos de Contacto: </p>
  	<div class="subscribe-buttons">
  <!-- Mail -->
<xsl:if test="normalize-space(/rss/channel/itunes:owner/itunes:email) != ''"> 
  <a class="subscribe-button">
    <xsl:attribute name="href">
      <xsl:value-of select="concat('mailto:', normalize-space(/rss/channel/itunes:owner/itunes:email))"/>
    </xsl:attribute>
    <img src="../img/mail.png" alt="Mail" />
  </a>
</xsl:if>

  <!-- Like -->
<xsl:if test="normalize-space(/rss/channel/itunes:owner/itunes:email) != '' and normalize-space(/rss/channel/om:like) = 'yes'"> 
  <a class="subscribe-button">
    <xsl:attribute name="href">
      <xsl:value-of select="concat(
        'mailto:', 
        normalize-space(/rss/channel/itunes:owner/itunes:email),
        '?subject=Like%20%E2%9D%A4%EF%B8%8F',
        '&amp;body=Me%20gusta%20mucho%20tu%20podcast%20',
        normalize-space(/rss/channel/title),
        '.%0A%0AEnviado%20desde%20Feedbueno.')"/>
    </xsl:attribute>
    <img src="../img/like.png" alt="like" />
  </a>
</xsl:if>

<!-- X (antes Twitter) -->
<xsl:if test="normalize-space(/rss/channel/om:x) != ''"> 
  <a class="subscribe-button" href="{/rss/channel/om:x}">
    <img src="../img/x.png" alt="X" />
  </a>
</xsl:if>

<!-- Facebook -->
<xsl:if test="normalize-space(/rss/channel/om:facebook) != ''"> 
  <a class="subscribe-button" href="{/rss/channel/om:facebook}">
    <img src="../img/facebook.png" alt="Facebook" />
  </a>
</xsl:if>

<!-- Instagram -->
<xsl:if test="normalize-space(/rss/channel/om:instagram) != ''"> 
  <a class="subscribe-button" href="{/rss/channel/om:instagram}">
    <img src="../img/instagram.png" alt="Instagram" />
  </a>
</xsl:if>

<!-- Bluesky -->
<xsl:if test="normalize-space(/rss/channel/om:bluesky) != ''"> 
  <a class="subscribe-button" href="{/rss/channel/om:bluesky}">
    <img src="../img/bluesky.png" alt="Bluesky" />
  </a>
</xsl:if>

<!-- whatsapp -->
<xsl:if test="normalize-space(/rss/channel/om:whatsapp) != ''"> 
  <a class="subscribe-button" href="{/rss/channel/om:whatsapp}">
    <img src="../img/whatsapp.png" alt="whatsapp" />
  </a>
</xsl:if>

<!-- telegram -->
<xsl:if test="normalize-space(/rss/channel/om:telegram) != ''"> 
  <a class="subscribe-button" href="{/rss/channel/om:telegram}">
    <img src="../img/telegram.png" alt="telegram" />
  </a>
</xsl:if>

<!-- discord -->
<xsl:if test="normalize-space(/rss/channel/om:discord) != ''"> 
  <a class="subscribe-button" href="{/rss/channel/om:discord}">
    <img src="../img/discord.png" alt="discord" />
  </a>
</xsl:if>
</div> 
</div>


<details>
  <summary><span style="font-weight: bold;">Descripción: </span>
    <span class="resumen">
      <xsl:value-of disable-output-escaping="yes" select="substring(/rss/channel/description, 1, 80)"/>...
    </span>
  </summary>
  <p>
    <xsl:value-of disable-output-escaping="yes" select="/rss/channel/description"/>
  </p>
</details>
  

  
        <xsl:for-each select="rss/channel/item">
         <div id="s{itunes:season}e{itunes:episode}"><div id="{om:sec}"></div></div>
 <div class="item">
          	<div class="item-content">
          	<div class="item-title">
          	<div><xsl:value-of select="title"/></div>
          	
                </div>
                
              <xsl:if test="itunes:image/@href != /rss/channel/itunes:image/@href">
  <img src="{itunes:image/@href}" width="75%" alt="Imagen del episodio"/>
</xsl:if>

                <div class="item-date">
                	<xsl:if test="itunes:episode">
                	  <xsl:text>s</xsl:text><xsl:value-of select="itunes:season"/>
  <xsl:text>e</xsl:text><xsl:value-of select="itunes:episode"/>
 - </xsl:if><xsl:value-of select="pubDate"/>
                </div>

  <audio controls="enabled" preload="none">
  <xsl:attribute name="src">
    <xsl:value-of select="enclosure/@url"/>
  </xsl:attribute>
</audio>

               
                
                <div class="item-description">
<xsl:variable name="desc" select="description"/>
<xsl:choose>
  <xsl:when test="contains($desc, '&lt;hr style=&quot;border:0;border-top:1px dashed #ccc;margin:20px 0;&quot; /&gt;')">
    <xsl:variable name="visible" select="substring-after($desc, '&lt;hr style=&quot;border:0;border-top:1px dashed #ccc;margin:20px 0;&quot; /&gt;')"/>
    <xsl:value-of select="$visible" disable-output-escaping="yes"/>
  </xsl:when>
  <xsl:otherwise>
    <xsl:value-of select="$desc" disable-output-escaping="yes"/>
  </xsl:otherwise>
</xsl:choose>
</div>
            </div>
          </div>
        </xsl:for-each>
        <div style="text-align: center;">
        <p>Powered by: </p>
      <p><img width="25%" src="../feedbueno.png" /></p>
        </div> 
      
      <button id="scrollTopBtn" title="Subir arriba">↑</button>
      <script>
        window.onscroll = function() {
          const btn = document.getElementById("scrollTopBtn");
          if (document.body.scrollTop > 100 || document.documentElement.scrollTop > 100) {
            btn.style.display = "block";
          } else {
            btn.style.display = "none";
          }
        };

        document.addEventListener("DOMContentLoaded", function() {
          document.getElementById("scrollTopBtn").addEventListener("click", function() {
            window.scrollTo({ top: 0, behavior: 'smooth' });
          });
        });
      </script>
</body>
    </html>
  </xsl:template>
</xsl:stylesheet>
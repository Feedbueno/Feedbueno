<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0"
  xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
  xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
  xmlns:om="https://omrey86.neocities.org/" 
  xmlns:content="http://purl.org/rss/1.0/modules/content/"
  xmlns:atom="http://www.w3.org/2005/Atom" >

  <xsl:output method="html" encoding="UTF-8" indent="yes"/>

  <xsl:template match="/">
    <html>
      <head>
        <title>
          <xsl:if test="/rss/channel/om:autor">
            <xsl:value-of select="rss/channel/om:autor"/> presenta: 
          </xsl:if>
          <xsl:value-of select="rss/channel/title"/>
        </title>

        <meta name="viewport" content="width=device-width, initial-scale=1"/>
        <style type="text/css">
          /* ... idéntico a tu CSS ... */
        </style>
      </head>
      <body>
        <!-- ... toda la parte de cabecera, botones, suscripciones, descripción de canal ... -->

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
                  <xsl:text> - </xsl:text>
                </xsl:if>
                <xsl:value-of select="pubDate"/>
              </div>

              <audio controls="enabled" preload="none" src="{enclosure/@url}"></audio>

              <div class="item-description">
                <xsl:variable name="desc-fragment">
                  <xsl:value-of select="content:encoded"/>
                </xsl:variable>

                <xsl:choose>
                  <xsl:when test="contains($desc-fragment, '&lt;hr style=&quot;border:0;border-top:1px dashed #ccc;margin:20px 0;&quot; /&gt;')">
                    <xsl:value-of 
                      select="substring-after($desc-fragment, '&lt;hr style=&quot;border:0;border-top:1px dashed #ccc;margin:20px 0;&quot; /&gt;')" 
                      disable-output-escaping="yes"/>
                  </xsl:when>
                  <xsl:otherwise>
                    <xsl:value-of select="$desc-fragment" disable-output-escaping="yes"/>
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
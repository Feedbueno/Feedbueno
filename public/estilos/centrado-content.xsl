<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0"
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:content="http://purl.org/rss/1.0/modules/content/">

  <xsl:output method="html" encoding="UTF-8" indent="yes"/>

  <xsl:template match="/">
    <html>
      <head>
        <title>
          <xsl:value-of select="/rss/channel/title"/>
        </title>
      </head>
      <body>
        <h1><xsl:value-of select="/rss/channel/title"/></h1>
        <xsl:for-each select="/rss/channel/item">
          <div class="item">
            <h2><xsl:value-of select="title"/></h2>
            <div class="content">
              <xsl:value-of select="content:encoded" disable-output-escaping="yes"/>
            </div>
          </div>
          <hr/>
        </xsl:for-each>
      </body>
    </html>
  </xsl:template>

</xsl:stylesheet>
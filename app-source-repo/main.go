package main

import (
	"github.com/gin-gonic/gin"
	"net/http"
)

func main() {
	s := gin.Default()
	s.GET("/", func(c *gin.Context) {
		c.JSON(http.StatusOK, "Hello World!")
	})
	s.Run(":8089")
}

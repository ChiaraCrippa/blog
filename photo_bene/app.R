library(shiny)
library(jpeg)


imgs<- list.files("/Users/chiara/personal_site/temp/photo/www", pattern=".jpg", full.names = TRUE)

ui <- fluidPage(
  
  sidebarLayout(
    sidebarPanel(
      actionButton("previous", "Previous"),
      actionButton("next", "Next")
    ),
    
    mainPanel(
      imageOutput("image")
      
    )
  )
)

server <- function(input, output, session) {
  
  index <- reactiveVal(1)
  
  observeEvent(input[["previous"]], {
    index(max(index()-1, 1))
  })
  observeEvent(input[["next"]], {
    index(min(index()+1, length(imgs)))
  })
  
  output$image <- renderImage({
    x <- imgs[index()] 
    list(src =x, filetype = "image/jpeg" , alt = "alternate text")
  }, deleteFile = FALSE)
}

shinyApp(ui = ui, server = server)


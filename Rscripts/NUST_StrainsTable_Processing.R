
### Step 1:

# If run standalone (not from run_nust_pipeline.R), configure here:
if (!exists("cfg")) {
  source("C:/Users/ivanv/Desktop/UMN_GIT/NUST_Data_Prep/nust_utils.R")
  source("C:/Users/ivanv/Desktop/UMN_GIT/NUST_Data_Prep/nust_config.R")
  cfg <- nust_config(
    year     = "2025",
    data_dir = "C:/Users/ivanv/Desktop/UMN_Projects/NUST_Projects/NUST_Data/2025/2025_NUST_Processing/"
  )
  setwd(cfg$data_dir)
}

library(reshape2)
Year <- cfg$year
Tests1 <- cfg$Tests1
Tests2 <- cfg$Tests2


FN <- c(list.files(".","^[UP]"))
table_data_filt_list <- list()

for(nFN in 1:length(FN)){

  Table_Fn <- FN[nFN]
  table_file2 <-  Table_Fn
  Test <- unlist(strsplit(Table_Fn,".csv"))
  table_conn <- file(table_file2, open = "r")

  header <- c()

  cnt <- 0
  while (TRUE) {
    line <- readLines(table_conn, n = 1)
    cnt <- cnt+1
    if (startsWith(line, ",")) {
      header<- c(header,line)
      next
    }else if (startsWith(line, "Ent.")){
      header<- c(header,line)
      headerRow <- cnt
      break
    }
  }

  table_data0 <- read.csv(Table_Fn, header = FALSE,skip=headerRow)
  colnames(table_data0) <- unlist(strsplit(header[headerRow],","))

### Extract the first two sub tables

  endRow <-  grep("YIELD",table_data0[,1])[1]
  table_data <- table_data0[c(1:endRow),]

###  Extract the first sub table

  REGRow1 <- grep("REGIONAL",table_data[,1])-2

  while(TRUE){
    if(is.na(as.numeric(as.character(table_data[REGRow1,1])))){
      REGRow1 <- REGRow1-1
      next
    }else{endRow1<- REGRow1
      break
    }
  }

  table_data_Pt1 <- table_data[c(1:endRow1),]

### Format Table Part1
  filtRowInd1 <- unlist(lapply(c(1:nrow(table_data_Pt1)),function(x) if(length(table_data_Pt1[x,])==length(which(is.na(table_data_Pt1[x,]) | as.character(table_data_Pt1[x,])==""))){x}else{NULL}))
  filtColInd1 <- unlist(lapply(c(1:ncol(table_data_Pt1)),function(x) if(length(table_data_Pt1[,x])==length(which(is.na(table_data_Pt1[,x]) | as.character(table_data_Pt1[,x])==""))){x}else{NULL}))

  if(length(filtRowInd1)>0){table_data_Pt1_filt0 <- table_data_Pt1[-filtRowInd1,]}else{table_data_Pt1_filt0 <- table_data_Pt1}
  if(length(filtColInd1)>0){table_data_Pt1_filt <- table_data_Pt1_filt0[,-filtColInd1]}else{table_data_Pt1_filt <- table_data_Pt1_filt0}
  colnames(table_data_Pt1_filt) <- unlist(strsplit(header[length(header)],","))[-filtColInd1]

### Extract the second sub table

  codeCol <- grep("Code",table_data)
  startRow2 <- which(table_data[,codeCol]=="Code")
  CVRow2 <- grep("Mean",table_data[,1])-1
  while(TRUE){
    if(as.character(table_data[CVRow2,1])==""){
      CVRow2 <- CVRow2-1
      next
    }else{endRow2<- CVRow2
    break
    }
  }

  table_data_Pt2 <- table_data[c(startRow2:endRow2),]

 ## Code col is present in previous row to the colnames
   strtInd <- grep("Strain",table_data_Pt2[,1])
  colnames(table_data_Pt2) <- table_data_Pt2[strtInd,]
  colnames(table_data_Pt2)[codeCol] <- "Code"

 #### Format Table Part2
  filtRowInd2 <- unlist(lapply(c(1:nrow(table_data_Pt2)),function(x) if(length(table_data_Pt2[x,])==length(which(is.na(table_data_Pt2[x,]) | as.character(table_data_Pt2[x,])==""))){x}else{NULL}))
  filtColInd2 <- unlist(lapply(c(1:ncol(table_data_Pt2)),function(x) if(length(table_data_Pt2[,x])==length(which(is.na(table_data_Pt2[,x]) | as.character(table_data_Pt2[,x])==""))){x}else{NULL}))

  if(length(filtRowInd2)>0){table_data_Pt2_filt0 <- table_data_Pt2[-c(1,filtRowInd2),]}else{table_data_Pt2_filt0 <- table_data_Pt2}
  if(length(filtColInd2)>0){table_data_Pt2_filt <- table_data_Pt2_filt0[,-filtColInd2]}else{table_data_Pt2_filt <- table_data_Pt2_filt0}

  codeCol2 <- which(colnames(table_data_Pt2_filt) %in% "Code")
  colnames(table_data_Pt2_filt)[codeCol2] <- "Code"

  strnCols <- which(colnames(table_data_Pt2_filt) %in% "Strain")

 if(length(strnCols)>1){
   colnames(table_data_Pt2_filt)[strnCols[2]] <- "Strain.2"
  }
##
  table_data_filt <- merge(table_data_Pt1_filt,table_data_Pt2_filt,by="Strain")

  table_data_filt_mod <- cbind.data.frame(rep(Year,nrow(table_data_filt)),rep(Test,nrow(table_data_filt)),table_data_filt)
  colnames(table_data_filt_mod)[c(1,2)] <- c("Year","Test")
  table_data_filt_list[[nFN]] <- table_data_filt_mod

  close(table_conn)
}

selCols <- c("Year","Test","Strain","Code","Traits","Comp.")


xComb <- c()
for(i in seq_along(table_data_filt_list)){
     x <- table_data_filt_list[[i]]
     colnames(x) <- gsub(" ","",colnames(x))
	 colInd <- match(selCols,colnames(x))

    xComb <- rbind.data.frame(xComb,x[,colInd])
 }


# lapply(c(1:length(table_data_filt_list)),function(x) length(which(colnames(table_data_filt_list[[1]]) %in% selCols)))

# strainsTable <- do.call(rbind.data.frame,lapply(table_data_filt_list,function(x){
	 # colnames(x) <- gsub(" ","",colnames(x))
	 # x[,c("Year","Test","Strain","Code","Traits","Comp.")]
# }))


strainsTable <- xComb
colnames(strainsTable) <- c("Year","Test","Strain","Descriptive Code","Unique traits","Gen.Comp.")


parentageTable <- do.call(rbind,lapply(table_data_filt_list,function(x) x[,c("Year","Test","Strain","Female","Male")]))
colnames(parentageTable) <- c("Year","Test","Strain","Female","Male")


#### Create a new strainID column without any formatting while retaining the original ID in OriginalStrain column

strainsTable$OriginalStrain <- strainsTable$Strain

strainsTableStrn1 <- clean_strain_annotations(strainsTable$OriginalStrain)

strainsTable$Strain <- strainsTableStrn1
strainsTable$`Unique traits` <- gsub(",",";",strainsTable$`Unique traits`)
strainsTable <- strainsTable[,c(c(1:3),ncol(strainsTable),c(4:(ncol(strainsTable)-1)))]

#####

dim(strainsTable)
#[1] 454   7

##
write.csv(strainsTable,"strainsTable_From_DataFiles.csv",row.names=F,quote=F)
write.csv(strainsTable,"strainsTable1.csv",row.names=F,quote=F)



##### Add Checks column to Strains Table

strainsTable1 <- read.csv("strainsTable1.csv")
ChecksTable1 <- read.csv("checksTable1.csv")

length(unique( ChecksTable1$Strain))

####
ChecksTable2 <- ChecksTable1
ChecksTable2$Strain <- gsub("[- ]", "", ChecksTable2$Strain)
length(unique(ChecksTable2$Strain))
#[1] 23

length(which(strainsTable1$Strain %in% ChecksTable2$Strain))
strainsTable1$Strain[which(strainsTable1$Strain %in% ChecksTable2$Strain)]
unqStrnChk <- unique(strainsTable1$Strain[which(gsub("[- ]", "",strainsTable1$Strain) %in% ChecksTable2$Strain)])
unqStrnChkRm <- setdiff(unique(ChecksTable2$Strain),gsub("[- ]", "",unqStrnChk))

### unqStrnChkRm
# [1] "ND17009GT"  "ND146120GT"
# Except for these two strains, all other strains are present in the strains table

# Add checks column to strainsTable1
unique(ChecksTable2$Strain)
chkInd <- which(gsub("[- ]", "",strainsTable1$Strain) %in% unique(ChecksTable2$Strain))
strainsTable1$Check <- 0
strainsTable1$Check[chkInd] <- 1

#####

write.csv(strainsTable1,"strainsTable1.csv",row.names=F,quote=F)

#####


parentageTableStrn1 <- clean_strain_annotations(parentageTable$Strain)

parentageTable$Strain <- parentageTableStrn1


parentageTable$Female[1:10]

parentageTable$Strain <- sapply(parentageTable$Strain, clean_strain_encoding)
parentageTable$Male <- sapply(parentageTable$Male, clean_strain_encoding)
parentageTable$Female <- sapply(parentageTable$Female, clean_strain_encoding)
#####

length(unique(strainsTable1$Strain))
#[1] 412
length(unique(parentageTable$Strain))
#[1] 412
###

write.csv(parentageTable,"parentageTable1.csv",row.names=FALSE,quote=FALSE)

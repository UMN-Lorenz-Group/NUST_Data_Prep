# Set working directory
source("C:/Users/ivanv/Desktop/UMN_GIT/NUST_Data_Prep/nust_utils.R")
setwd("C:/Users/ivanv/Desktop/UMN_Projects/NUST_Projects/NUST_Data/2025/2025_NUST_Processing/")
library(reshape2)

# Define year and test sets
Year <- "2025"
Tests1 <- c("UT00","UT0","UTI","UTII","UTIII","UTIV","PTI","PTIIA","PTIIB","PTIIIA","PTIIIB","PTIV")
Tests2 <- paste(c("UT0","UTI","UTII","UTIII","UTIV"),"TM",sep="")
Tests3 <- paste(c("Seed Traits UT0", "Seed Traits UTI", "Seed Traits UTII", "Seed Traits UTIII", "Seed Traits UTIV"), "TM", sep = "")

# Read lookup table
Cal_Julian_Lookup_2025 <- read.csv("Cal_Date_JulDay_LookUp_2025.csv", header = TRUE)

# Initialize output list
PhenotypesTable_Out_List <- list()
SDTraitValues <- c(FALSE, TRUE)  # Logical values instead of character

######################################################
# Loop over trait types (Agronomic vs. Seed Composition)
for(nSD in seq_along(SDTraitValues)) {
  
  # Initialize lists
  PhenotypesTable_List <- list()
  MetaTable_List <- list()
  LocationsTable_List <- list()
  
  # Define trait-specific variables
  SDTraits <- SDTraitValues[nSD]
  
  if(SDTraits) {
    SdTraits <- c("FATTY ACID, PALMITIC (%)", "FATTY ACID, STEARIC (%)", "FATTY ACID, OLEIC (%)", 
                  "FATTY ACID, LINOLEIC (%)", "FATTY ACID, LINOLENIC (%)")
    SdTraitNames <- c("PALMITIC", "STEARIC", "OLEIC", "LINOLEIC", "LINOLENIC")
    
    SdTraitsSUG <- c("SEED SUGAR, SUCROSE (%)", "SEED SUGAR, RAFFINOSE (%)", 
                     "SEED SUGAR, STACHYOSE (%)", "SEED SUGAR, TOTAL (%)")
    SdTraitNamesSUG <- c("SUCROSE", "RAFFINOSE", "STACHYOSE", "TOTAL")
    
    Tests <- Tests3
    Traits <- c(SdTraits,SdTraitsSUG)
    TraitNames <- c(SdTraitNames, SdTraitNamesSUG)
  }else{ 
    Traits <- c("YIELD (bu/a)", "YIELD RANK", "MATURITY (date)", "LODGING (score)", 
                "PLANT HEIGHT (inches)", "SEED SIZE (g/100)", "SEED QUALITY (score)", 
                "PROTEIN (%)", "OIL (%)")
    TraitNames <- c("YIELD", "MATURITY", "LODGING", "PLANT HEIGHT", "SEED SIZE", 
                    "SEED QUALITY", "PROTEIN", "OIL")
    Tests <- c(Tests1, Tests2)
  }
  
  # Process each test file
  for(Test in Tests){
   
    fileName <- paste0(Test, ".csv")
    
    if (!file.exists(fileName)) {
      warning(paste("File not found:", fileName))
      next
    }
    
    # Read and clean data
    Trial_File <- read.csv(fileName, header = TRUE, stringsAsFactors = FALSE)
    Trial_File <- as.data.frame(lapply(Trial_File, as.character))
    
    # Remove empty rows and columns
    Trial_File_Filt <- Trial_File[rowSums(is.na(Trial_File) | Trial_File == "") != ncol(Trial_File), ]
    Trial_File_Filt <- Trial_File_Filt[, colSums(is.na(Trial_File_Filt) | Trial_File_Filt == "") != nrow(Trial_File_Filt)]
    
    # Clean strain names
    Trial_File_Filt$X <- sapply(Trial_File_Filt$X, clean_strain_encoding)
    
	### UTITM Seed traits test doesn't contain sugar trait values 
	if(SDTraits & (Test == "Seed Traits UTITM")){ 
	   Traits <- (SdTraits)
       TraitNames <- (SdTraitNames)
	}else if(SDTraits & (Test != "Seed Traits UTITM")){
	  Traits <- c(SdTraits,SdTraitsSUG)
      TraitNames <- c(SdTraitNames, SdTraitNamesSUG)
	} 
	
	# Extract relevant data
    # beginCol <- which(colSums(sapply(TraitNames, function(y) grepl(y, Trial_File_Filt, fixed = TRUE))) >= length(TraitNames))
    beginCol <- which(sum(sapply(TraitNames, function(y) grepl(y, Trial_File_Filt, fixed = TRUE))) >= length(TraitNames))
	
	if (length(beginCol) == 0) {
      warning(paste("No trait column found in:", fileName))
      next
    }
    
    # Process trait tables
    TraitsTable_List <- list()
    TrtTab_Filt_Lng_List <- list()
    
   if(SDTraits){
	
     for(nTrt in seq_along(TraitNames)){
		  # Locate trait rows
		  trt <- TraitNames[nTrt]
		  trtIndx <- unlist(sapply(TraitNames, function(y) grep(paste(" ",y,sep=""), Trial_File_Filt[, beginCol], fixed = FALSE)))
		  
		  if(length(trtIndx) == 0) next
      	  
		 
		   # Trts1
		   # Extract trait data
		   if (nTrt < length(TraitNames)){
		   ###Between LINOLENIC and Sugar traits, there are other many other rows
			if(trt != "LINOLENIC"){  
			 Filt0 <- Trial_File_Filt[trtIndx[nTrt]:(trtIndx[nTrt + 1] - 1), beginCol:ncol(Trial_File_Filt)]
			}else if(trt == "LINOLENIC"){ 
			 
			 Filt00 <-  Trial_File_Filt[trtIndx[nTrt]:(trtIndx[nTrt + 1] - 1), beginCol:ncol(Trial_File_Filt)]
			 finIndx <- grep("SEED COMPOSITION",Filt00[,beginCol])
			 Filt0 <- Filt00[c(1:(finIndx-1)), beginCol:ncol(Filt00)] 
			}
		   }else{
			Filt0 <- Trial_File_Filt[trtIndx[nTrt]:nrow(Trial_File_Filt), beginCol:ncol(Trial_File_Filt)]
		   }
		  Filt0 <- Filt0[,colSums(is.na(Filt0) | Filt0 == "") != nrow(Filt0)]
		  print(dim(Filt0))
		  TraitsTable_List[[nTrt]] <- Filt0
	 }	
		# Process trait tables into long format
	 for(nTrt in seq_along(TraitNames)) {
		  TrtTab0 <- as.data.frame(TraitsTable_List[[nTrt]])
		  cNames <- apply(TrtTab0[1:4,],2,function(x) paste(x,collapse="_"))
		  cNames <- gsub("[-_]","",cNames)
		  colnames(TrtTab0) <- cNames
		  colnames(TrtTab0)[1] <- "Strain"
		  strtInd <- as.numeric(grep("Strain",TrtTab0[,"Strain"]))
		  if(length(strtInd) >0){TrtTab <- TrtTab0[-c(1:strtInd),]}else{TrtTab <- TrtTab0}
		  colnames(TrtTab) <- gsub("([A-Z][a-z]*)([A-Z][A-z])$","\\1_\\2",colnames(TrtTab))
			
		  TrtTab_Filt_Lng <- melt(TrtTab, id.vars = "Strain")
		  colnames(TrtTab_Filt_Lng) <- c("Strain", "Location", Traits[nTrt])
		  TrtTab_Filt_Lng_List[[nTrt]] <- TrtTab_Filt_Lng[order(TrtTab_Filt_Lng$Strain), ]
	 }
		
		# Merge all trait tables
		TrtTab_Out_Comb0 <- Reduce(function(x, y) merge(x, y, by = c("Strain", "Location"), all = TRUE), TrtTab_Filt_Lng_List)
		TrtTab_Out_Comb00 <- TrtTab_Out_Comb0[grep("contamination",TrtTab_Out_Comb0$Strain,invert=T),]
		TrtTab_Out_Comb <- TrtTab_Out_Comb00[grep("UNIFORM",TrtTab_Out_Comb00$Strain,invert=T),]
		
		# Assign column names
		colnames(TrtTab_Out_Comb)[1:2] <- c("Strain", "Location")
		TrtTab_Out_Comb$Test <- Test
        TrtTab_Out_Comb$Year <- "2025"
	     # Append to list
        PhenotypesTable_List[[Test]] <- TrtTab_Out_Comb
    }
   

   if(!SDTraits){

		for(nTrt in seq_along(Traits)){
		  # Locate trait rows
		  trt <- Traits[nTrt]
		  trtIndx <- unlist(sapply(TraitNames, function(y) grep(y,Trial_File_Filt[, beginCol], fixed = FALSE)))
		  
		  if(length(trtIndx) == 0) next

			if(nTrt < length(Traits)){
				Filt0 <- Trial_File_Filt[trtIndx[nTrt]:(trtIndx[nTrt + 1] - 1), beginCol:ncol(Trial_File_Filt)]
			}else{
				Filt0 <- Trial_File_Filt[trtIndx[nTrt]:nrow(Trial_File_Filt), beginCol:ncol(Trial_File_Filt)]
			}
			Filt0 <- Filt0[,colSums(is.na(Filt0) | Filt0 == "") != nrow(Filt0)]
			print(dim(Filt0))
			TraitsTable_List[[nTrt]] <- Filt0
		}   
	
		# Process trait tables into long format
		for (nTrt in seq_along(Traits)) {
		  TrtTab0 <- as.data.frame(TraitsTable_List[[nTrt]])
		  cNames <- apply(TrtTab0[1:4,],2,function(x) paste(x,collapse="_"))
		  cNames <- gsub("[-_]","",cNames)
		  colnames(TrtTab0) <- cNames
		  colnames(TrtTab0)[1] <- "Strain"
		  strtInd <- as.numeric(grep("Strain",TrtTab0[,"Strain"]))
		  if(length(strtInd) >0){TrtTab <- TrtTab0[-c(1:strtInd),]}else{TrtTab <- TrtTab0}
		  colnames(TrtTab) <- gsub("([A-Z][a-z]*)([A-Z][A-z])$","\\1_\\2",colnames(TrtTab))
			
		  TrtTab_Filt_Lng <- melt(TrtTab, id.vars = "Strain")
		  colnames(TrtTab_Filt_Lng) <- c("Strain", "Location", Traits[nTrt])
		  TrtTab_Filt_Lng_List[[nTrt]] <- TrtTab_Filt_Lng[order(TrtTab_Filt_Lng$Strain), ]
		}
    
    # Merge all trait tables
     TrtTab_Out_Comb0 <- Reduce(function(x, y) merge(x, y, by = c("Strain", "Location"), all = TRUE), TrtTab_Filt_Lng_List)
	 TrtTab_Out_Comb00 <- TrtTab_Out_Comb0[grep("contamination",TrtTab_Out_Comb0$Strain,invert=T),]
	 TrtTab_Out_Comb <- TrtTab_Out_Comb00[grep("UNIFORM",TrtTab_Out_Comb00$Strain,invert=T),]
	
	# Assign column names
     colnames(TrtTab_Out_Comb)[1:2] <- c("Strain", "Location")
	 TrtTab_Out_Comb$Test <- Test
     TrtTab_Out_Comb$Year <- "2025"
	 # Append to list
     PhenotypesTable_List[[Test]] <- TrtTab_Out_Comb
    }
  }	
  # Combine and store results
  if (!SDTraits) {
    PhenotypesTable <- do.call(rbind.data.frame, PhenotypesTable_List)
  }else{
    maxCols <- max(sapply(PhenotypesTable_List, ncol))
    maxColnames <- colnames(PhenotypesTable_List[[which.max(sapply(PhenotypesTable_List, ncol))]])
    
    PhenotypesTable <- do.call(rbind.data.frame, lapply(PhenotypesTable_List, function(x) {
      if(ncol(x) < maxCols){
	    
		cNamesNA <- setdiff(maxColnames,colnames(x))
	    naDF <- as.data.frame(matrix(NA, nrow = nrow(x), ncol = (maxCols - ncol(x))))
		colnames(naDF) <- cNamesNA
        x <- cbind.data.frame(x,naDF)
		
      }
	  cNamesX <- colnames(x)
	  cNamesXOrd <- cNamesX[match(maxColnames,cNamesX)]
	  xOrd <- x[,cNamesXOrd]
      return(xOrd)
    }))
  }
  
  # Store in final list
  PhenotypesTable_Out_List[[nSD]] <- PhenotypesTable
}

names(PhenotypesTable_Out_List) <- c("AgTrts","SdTrts")


#############################################################################################################################################
#### Format Phenotype tables 
# Extract phenotype data
Phenotypes_AgTr0 <- PhenotypesTable_Out_List$`AgTrts`

patRm <- c("Data not included","C.V.","Date Planted","Days to Mature","L.S.D.","Location Mean","PRELIMINARY TEST","Row sp.","UNIFORM TEST","Reps","Rows/Plot","\\h")
patRmInd <- unique(unlist(lapply(patRm,function(x) grep(x,Phenotypes_AgTr0$Strain,ignore.case=T))))
if(length(patRmInd) >0){Phenotypes_AgTr00 <- Phenotypes_AgTr0[-patRmInd,]}else{Phenotypes_AgTr00 <- Phenotypes_AgTr0}


Phenotypes_AgTr000 <- Phenotypes_AgTr00[grep("Mean",Phenotypes_AgTr00$Location,invert=TRUE),]

nullInd <- which(Phenotypes_AgTr000$Strain %in% "")
if(length(nullInd)>0){Phenotypes_AgTr1 <- Phenotypes_AgTr000[-nullInd,]}else{Phenotypes_AgTr1 <- Phenotypes_AgTr000}
dim(Phenotypes_AgTr1)
#[1] 5082   13

############
Phenotypes_AgTr <- Phenotypes_AgTr1[Phenotypes_AgTr1$Location != " ",]
# Handling missing Strain names
strNAInd <- which(is.na(Phenotypes_AgTr$Strain))
# Verify missing values
anyNA(Phenotypes_AgTr$Strain)
#[1] FALSE

###############################################
# **Formatting Conventions**
# Standardize location names
Phenotypes_AgTr$Location <- gsub("WestLafayette_IN", "Lafayette_IN", Phenotypes_AgTr$Location)

# Remove extra characters from strain names
Phenotypes_AgTr$Strain <- gsub("_","-",Phenotypes_AgTr$Strain)
Phenotypes_AgTr$Strain <- gsub("[\\*]*$","",Phenotypes_AgTr$Strain)
#Phenotypes_AgTr$Strain <- gsub(" ","-",Phenotypes_AgTr$Strain)
Phenotypes_AgTr$OriginalStrain <- Phenotypes_AgTr$Strain
#Phenotypes_AgTr$Strain <- gsub("\\(E\\)|\\(L\\)|\\(I\\)|\\(SCN\\)| ", "", Phenotypes_AgTr$Strain)
 

 
length(unique(Phenotypes_AgTr$OriginalStrain))
#[1] 421

length(unique(Phenotypes_AgTr$Strain))
#[1] 421
 
# Replace "-" with "_" in the Year-Test and UniqueID columns (except for strain names)
#Phenotypes_AgTr$UniqueID1 <- gsub("-","_",Phenotypes_AgTr$UniqueID1)

####
unique(Phenotypes_AgTr$Location)
Phenotypes_AgTr$Location <- gsub("([A-Z][a-z]*)([A-Z][A-Z]\\*)$","\\1_\\2",Phenotypes_AgTr$Location)
Phenotypes_AgTr$Location <- gsub("([A-Z][a-z]*)([A-Z][A-Z])$","\\1_\\2",Phenotypes_AgTr$Location)
Phenotypes_AgTr$Location <- gsub("S_AS","_SAS",Phenotypes_AgTr$Location)
Phenotypes_AgTr$Location <- gsub("O_NT","_ONT",Phenotypes_AgTr$Location) 
Phenotypes_AgTr$Location <- gsub("Q_UE","_QUE",Phenotypes_AgTr$Location)
Phenotypes_AgTr$Location <- gsub("__","_",Phenotypes_AgTr$Location)
Phenotypes_AgTr$Location <- gsub("\\*$","",Phenotypes_AgTr$Location)
Phenotypes_AgTr$Location <- gsub("\\'","",Phenotypes_AgTr$Location)
unique(Phenotypes_AgTr$Location)
####

Phenotypes_AgTr$UniqueID <- paste(Phenotypes_AgTr[,"Strain"],Phenotypes_AgTr[,"Location"],Phenotypes_AgTr[,"Test"],sep="_")
length(unique(Phenotypes_AgTr$UniqueID))

#[1] 4760

dim(Phenotypes_AgTr)
#[1] 5044   18

# Create a unique ID column
Phenotypes_AgTr$UniqueID1 <- paste(Phenotypes_AgTr[,"Year"], Phenotypes_AgTr[,"UniqueID"], sep = "_")
### 
Phenotypes_AgTr_DF <- as.data.frame(Phenotypes_AgTr)
dim(Phenotypes_AgTr_DF)
#[1]  5044   18

# Remove duplicate rows based on UniqueID1
dupIndAg <- which(duplicated(Phenotypes_AgTr_DF$UniqueID1))
if(length(dupIndAg)>0){Phenotypes_AgTr_DF_Filt0 <- Phenotypes_AgTr_DF[-dupIndAg,]}else{Phenotypes_AgTr_DF_Filt0 <- Phenotypes_AgTr_DF}

dim(Phenotypes_AgTr_DF_Filt0)
#[1] 4760   16

length(unique(Phenotypes_AgTr_DF_Filt0$Strain))
#[1] 421

#chkUnqID <- unlist(lapply(dupUniqueID,function(x) grep(x,Phenotypes_AgTr_DF_Filt0$UniqueID1)))
###

rmInd1 <- grep("Mean",Phenotypes_AgTr_DF_Filt0[,"UniqueID1"])
if(length(rmInd1)>0){Phenotypes_AgTr_DF_Filt1 <- Phenotypes_AgTr_DF_Filt0[-rmInd1,]}else{Phenotypes_AgTr_DF_Filt1 <- Phenotypes_AgTr_DF_Filt0}
dim(Phenotypes_AgTr_DF_Filt1)
#[1]4760   16

### 
Phenotypes_AgTr$City <- unlist(lapply(Phenotypes_AgTr$Location,function(x) unlist(strsplit(x,"_")[[1]])[1]))
Phenotypes_AgTr$State <- unlist(lapply(Phenotypes_AgTr$Location,function(x) unlist(strsplit(x,"_")[[1]])[2]))

#############################################################################################################################################
### SD Traits Table processing
Phenotypes_SdTr0 <- PhenotypesTable_Out_List$`SdTrts`

patRm <- c("Data not included","C.V.","Date Planted","Days to Mature","L.S.D.","Location Mean","PRELIMINARY TEST","Row sp.","UNIFORM TEST","Reps","Rows/Plot")
patRmSDInd <- unique(unlist(lapply(patRm,function(x) grep(x,Phenotypes_SdTr0$Strain,ignore.case=T))))
if(length(patRmSDInd) >0){Phenotypes_SdTr <- Phenotypes_SdTr0[-patRmSDInd,]}else{Phenotypes_SdTr <- Phenotypes_SdTr0}
dim(Phenotypes_SdTr)
#[1] 503  13

Phenotypes_SdTr$UniqueID <- paste(Phenotypes_SdTr[,"Strain"],Phenotypes_SdTr[,"Location"],Phenotypes_SdTr[,"Test"],sep="_")
length(unique(Phenotypes_SdTr$UniqueID ))
#[1] 503

Phenotypes_SdTr$UniqueID1 <- paste(Phenotypes_SdTr$Year,Phenotypes_SdTr$UniqueID,sep="_")
###
Phenotypes_SdTr_DF <- as.data.frame(Phenotypes_SdTr)
dim(Phenotypes_SdTr_DF)
#[1] 503  15

## 

dupInd <-  which(duplicated(Phenotypes_SdTr_DF[,"UniqueID"]))
if(length(dupInd)>0){
  Phenotypes_SdTr_DF_Filt <- Phenotypes_SdTr_DF[-dupInd,]
}else{Phenotypes_SdTr_DF_Filt <- Phenotypes_SdTr_DF}

dim(Phenotypes_SdTr_DF_Filt)
#[1] 503  15

Phenotypes_SdTr_DF_Filt[,"UniqueID1"] <- gsub("2025[-_]Seed Traits ","2025_",Phenotypes_SdTr_DF_Filt[,"UniqueID1"])
rmInd1 <- grep("Mean",Phenotypes_SdTr_DF_Filt[,"UniqueID1"])
if(length(rmInd1)>0){Phenotypes_SdTr_DF_Filt1 <- Phenotypes_SdTr_DF_Filt[-rmInd1,]}else{Phenotypes_SdTr_DF_Filt1 <- Phenotypes_SdTr_DF_Filt}
dim(Phenotypes_SdTr_DF_Filt1)
#[1] 435  15


Phenotypes_SdTr_DF_Filt1$UniqueID1 <- gsub("Seed Traits ","",Phenotypes_SdTr_DF_Filt1$UniqueID1)

##
NAIndSdTr <- which(is.na(Phenotypes_SdTr_DF_Filt1[,"Strain"]))
NAIndSdTr
#integer(0)

### 
Phenotypes_SdTr_DF_Filt1$Location <- as.character(Phenotypes_SdTr_DF_Filt1$Location)
Phenotypes_SdTr_DF_Filt1$City <- unlist(lapply(Phenotypes_SdTr_DF_Filt1$Location,function(x) unlist(strsplit(x,"_")[[1]])[1]))
Phenotypes_SdTr_DF_Filt1$State <- unlist(lapply(Phenotypes_SdTr_DF_Filt1$Location,function(x) unlist(strsplit(x,"_")[[1]])[2]))
Phenotypes_SdTr_DF_Filt1$UniqueID1 <- gsub("Seed Traits ","",Phenotypes_SdTr_DF_Filt1$UniqueID1)

### Merge AgTraits and SdTraits
Phenotypes_AgSd_Tr <- merge(Phenotypes_AgTr_DF_Filt1,Phenotypes_SdTr_DF_Filt1,by="UniqueID1",all=TRUE)
dim(Phenotypes_AgSd_Tr)
#[1] 4854   32

grep("\\.y",colnames(Phenotypes_AgSd_Tr),value=T)
yColRmInd <- grep("\\.y",colnames(Phenotypes_AgSd_Tr))
Phenotypes_AgSd_Tr_Filt <- Phenotypes_AgSd_Tr[,-yColRmInd]
colnames(Phenotypes_AgSd_Tr_Filt) <- gsub("\\.x","",colnames(Phenotypes_AgSd_Tr_Filt))

###
rmInd1 <- grep("Mean",Phenotypes_AgSd_Tr_Filt[,"UniqueID1"])
if(length(rmInd1)>0){
  Phenotypes_AgSd_Tr_Filt1 <- Phenotypes_AgSd_Tr_Filt[-rmInd1,]
}else{Phenotypes_AgSd_Tr_Filt1 <- Phenotypes_AgSd_Tr_Filt}

##
dim(Phenotypes_AgSd_Tr_Filt1)
#[1] 4854   27

### 




### Formatting Conventions (Cleiton)
# 
# Verify consistency of naming convention for locations with previously used names (from NUST_Location_Names.xlsx)
# Ex.: Lafayette_IN instead of WestLafayette_IN
# Use underscore instead of "-" as the separator in the Year_Test column as well as between the genotype name and the location code.   
# Only the genotype names have "-".
# Remove information of the checks in parenthesis: delete space and the info in the parenthesis. Ex:. (L), (SCN), (E)
# Preserve the trait naming convention: 
# YieldBuA	YieldRank	Maturity	Lodging	Height	SeedSize	SeedQuality	Protein	Oil	DescriptiveCode	Chlorosis	Shattering	GreenStem	SDS	Frogeye	LeafShape	PALMITIC	STEARIC	OLEIC	LINOLEIC LINOLENIC,
# No need for the measurement unit in parenthesis
# Once you work with the traited material, please remember to add "RR" to the test name (instead of "TM")

#Format Strain Names to remove other information 

Phenotypes_AgSd_Tr_Filt1$OriginalStrain <- Phenotypes_AgSd_Tr_Filt1$Strain
Phenotypes_AgSd_Tr_Filt1$Strain <- gsub("\\(E\\)|\\(L\\)|\\(I\\)|\\(SCN\\)| ","",Phenotypes_AgSd_Tr_Filt1$Strain)

length(unique(Phenotypes_AgSd_Tr_Filt1$Strain))
#[1] 414
length(unique(Phenotypes_AgSd_Tr_Filt1$OriginalStrain))
#[1] 422

### Locations with NA
anyNA(Phenotypes_AgSd_Tr_Filt1$Location)
which(Phenotypes_AgSd_Tr_Filt1$Location == "")
#integer(0)
naLocInd <- which(is.na(Phenotypes_AgSd_Tr_Filt1$Location))
length(naLocInd)
#[1] 94

table(Phenotypes_AgSd_Tr_Filt1$Location[naLocInd] )

### Extract Strain, OriginalStrain and Location info for rows with missing info from UniqueID

Phenotypes_AgSd_Tr_Filt1[naLocInd,"Strain"] <- unlist(lapply(Phenotypes_AgSd_Tr_Filt1[naLocInd,"UniqueID1"],function(x) unlist(strsplit(x,"_")[[1]])[2]))

Phenotypes_AgSd_Tr_Filt1[naLocInd,"Location"] <- unlist(lapply(Phenotypes_AgSd_Tr_Filt1[naLocInd,"UniqueID1"],function(x) 
           { x <- unlist(strsplit(x,"_")[[1]])
		     paste(x[3],x[4],sep="_")
           }))
		   

anyNA(Phenotypes_AgSd_Tr_Filt1$Location)
#[1] FALSE

Phenotypes_AgSd_Tr_Filt1[naLocInd,"OriginalStrain"]  <- Phenotypes_AgSd_Tr_Filt1[naLocInd,"Strain"] 
anyNA(Phenotypes_AgSd_Tr_Filt1$Strain)
#[1] FALSE

Phenotypes_AgSd_Tr_Filt1$City[naLocInd]  <- unlist(lapply(Phenotypes_AgSd_Tr_Filt1[naLocInd,"Location"],function(x) unlist(strsplit(x,"_")[[1]])[1]))
Phenotypes_AgSd_Tr_Filt1$State[naLocInd] <- unlist(lapply(Phenotypes_AgSd_Tr_Filt1[naLocInd,"Location"],function(x) unlist(strsplit(x,"_")[[1]])[2]))

naStInd <- which(is.na(Phenotypes_AgSd_Tr_Filt1$State))
Phenotypes_AgSd_Tr_Filt1[naStInd,]


####
naStrnInd <- which(is.na(Phenotypes_AgSd_Tr_Filt1$Strain))
patToRm <- c("Reps","Rows/Plot")
patToRmInd <- which(Phenotypes_AgSd_Tr_Filt1$Strain %in% patToRm)
Phenotypes_AgSd_Tr_Filt1[patToRmInd,]

####
anyNA(Phenotypes_AgSd_Tr_Filt1$OriginalStrain)
# FALSE
length(which(is.na(Phenotypes_AgSd_Tr_Filt1$OriginalStrain)))
#[1] 0

naYrInd <- which(is.na(Phenotypes_AgSd_Tr_Filt1$Year))
length(naYrInd)
#[1] 94
anyNA(Phenotypes_AgSd_Tr_Filt1$Year)
#[1] TRUE

Phenotypes_AgSd_Tr_Filt1$Year[naYrInd] <- unlist(lapply(Phenotypes_AgSd_Tr_Filt1$UniqueID1[naYrInd],function(x) unlist(strsplit(x,"_")[[1]])[1]))
naTstInd <- which(is.na(Phenotypes_AgSd_Tr_Filt1$Test))
length(naTstInd)
# [1] 94
###

naTsts <- unlist(lapply(Phenotypes_AgSd_Tr_Filt1$UniqueID1[naTstInd],function(x) { 
    ln <- unlist(strsplit(x,"_")[[1]])
	ln[length(ln)]
}))

Phenotypes_AgSd_Tr_Filt1$Test[naTstInd] <- gsub("Seed Traits ","",naTsts)
table(Phenotypes_AgSd_Tr_Filt1$Test)
# PTI   PTIIA   PTIIB  PTIIIA  PTIIIB    PTIV     UT0    UT00   UT0TM     UTI    UTII   UTIII UTIIITM  UTIITM   UTITM    UTIV  UTIVTM 
# 434     408     408     440     396     342     275      96     266     288     560     520     238     294     185     232     135 
anyNA(Phenotypes_AgSd_Tr_Filt1$Test)
#[1] FALSE

### 
naUnqIDnd <- which(is.na(Phenotypes_AgSd_Tr_Filt1$UniqueID))
length(naUnqIDnd)
#[1] 94

naUnqIDs <- unlist(lapply(Phenotypes_AgSd_Tr_Filt1$UniqueID1[naUnqIDnd],function(x) { 
    ln <- gsub("2025_","",x)
	ln
}))
Phenotypes_AgSd_Tr_Filt1$UniqueID[naUnqIDnd] <- naUnqIDs

### 
apply(Phenotypes_AgSd_Tr_Filt1,2,function(x) anyNA(x))

############
dim(Phenotypes_AgSd_Tr_Filt1)
#[1] 4854   27

noLocInd <- which(Phenotypes_AgSd_Tr_Filt1$Location== "")
if(length(noLocInd) >0) {Phenotypes_AgSd_Tr_Filt_DF <- Phenotypes_AgSd_Tr_Filt1[-noLocInd,]} else{Phenotypes_AgSd_Tr_Filt_DF <- Phenotypes_AgSd_Tr_Filt1}
dim(Phenotypes_AgSd_Tr_Filt_DF)
#[1] 4854   27

Phenotypes_AgSd_Tr_Filt_DF <- as.data.frame(Phenotypes_AgSd_Tr_Filt_DF) #cbind.data.frame(Phenotypes_AgTr_ID_Cols1,Phenotypes_AgTr_ID_Cols2,Phenotypes_AgSd_Tr_Filt_Tab)
Phenotypes_AgSd_Tr_Filt_DF[,"Location"] <- gsub(" ","",Phenotypes_AgSd_Tr_Filt_DF[,"Location"])
#apply(Phenotypes_AgSd_Tr_Filt_DF[,1:4],2,table)

####
unique(Phenotypes_AgSd_Tr_Filt_DF$Location)
Phenotypes_AgSd_Tr_Filt_DF$Location <- gsub("([A-Z][a-z]*)([A-Z][A-Z]\\*)$","\\1_\\2",Phenotypes_AgSd_Tr_Filt_DF$Location)
Phenotypes_AgSd_Tr_Filt_DF$Location <- gsub("([A-Z][a-z]*)([A-Z][A-Z])$","\\1_\\2",Phenotypes_AgSd_Tr_Filt_DF$Location)
Phenotypes_AgSd_Tr_Filt_DF$Location <- gsub("S_AS","_SAS",Phenotypes_AgSd_Tr_Filt_DF$Location)
Phenotypes_AgSd_Tr_Filt_DF$Location <- gsub("O_NT","_ONT",Phenotypes_AgSd_Tr_Filt_DF$Location) 
Phenotypes_AgSd_Tr_Filt_DF$Location <- gsub("Q_UE","_QUE",Phenotypes_AgSd_Tr_Filt_DF$Location)
Phenotypes_AgSd_Tr_Filt_DF$Location <- gsub("__","_",Phenotypes_AgSd_Tr_Filt_DF$Location)
Phenotypes_AgSd_Tr_Filt_DF$Location <- gsub("\\*$","",Phenotypes_AgSd_Tr_Filt_DF$Location)

unique(Phenotypes_AgSd_Tr_Filt_DF$Location)
####

Phenotypes_AgSd_Tr_Filt_DF1 <- Phenotypes_AgSd_Tr_Filt_DF
Phenotypes_AgSd_Tr_Filt_DF <- Phenotypes_AgSd_Tr_Filt_DF1[Phenotypes_AgSd_Tr_Filt_DF1$Location!="",]

unique(Phenotypes_AgSd_Tr_Filt_DF$Location)
# Check distributions of Year, Test, Location, and State

Phenotypes_AgSd_Tr_Filt_DF$City <- unlist(lapply(Phenotypes_AgSd_Tr_Filt_DF$Location,function(x) unlist(strsplit(x,"_")[[1]])[1]))
Phenotypes_AgSd_Tr_Filt_DF$State <- unlist(lapply(Phenotypes_AgSd_Tr_Filt_DF$Location,function(x) unlist(strsplit(x,"_")[[1]])[2]))

table(Phenotypes_AgSd_Tr_Filt_DF$City)
table( Phenotypes_AgSd_Tr_Filt_DF$State)
# IA  IL  IN  KS  MI  MN  MO  ND  NE  OH ONT QUE SAS 
# 774 976 803 134 324 450 244 287 849 219 370  33  16 


anyNA(Phenotypes_AgSd_Tr_Filt_DF$Strain)
#[1] FALSE
 anyNA(Phenotypes_AgSd_Tr_Filt_DF$OriginalStrain)
#[1] FALSE

#### NUST Locations Table 

# Load NUST location reference
NUST_Locations_Ref <- read.csv("NUST_Location_Names.csv", header = TRUE)

# Extract unique NUST location names
NUST_Locations <- unlist(as.vector(NUST_Locations_Ref[,c("Location1", "Location2")]))
NUST_Location_Names <- NUST_Locations[NUST_Locations != ""]
NUST_Locations_Lev <- unique(NUST_Location_Names)

# Extract unique data location names
Data_Location_Names <- unique(Phenotypes_AgSd_Tr_Filt_DF[,"Location"]) #, Phenotypes_AgSd_Tr_Filt_DF[,"State"], sep = "_")
Data_Locations_Lev <- unique(gsub(" ", "", Data_Location_Names))

# Compare data and reference locations
remNames1 <- setdiff(Data_Locations_Lev, NUST_Locations_Lev)
remLocNames1 <- sapply(strsplit(remNames1, "_"), function(x) x[1])

remNames2 <- setdiff(NUST_Locations_Lev, Data_Locations_Lev)
remLocNames2 <- sapply(strsplit(remNames2, "_"), function(x) x[1])

# Create matching tables for unresolved location names
Match_Tab1 <- do.call(rbind, lapply(remLocNames1, function(x) {
  match_indices <- grep(x, remLocNames2)
  if (length(match_indices) > 0) {
    c(x, remLocNames2[match_indices[1]])
  } else {
    NULL
  }
}))
Match_Tab1 <- Match_Tab1[-c(1:2),]

Match_Tab2 <- do.call(rbind, lapply(remLocNames2, function(x) {
  match_indices <- grep(x, remLocNames1)
  if (length(match_indices) > 0) {
    c(remLocNames1[match_indices[1]], x)
  } else {
    NULL
  }
}))

# Combine match tables and clean up
LocName_Match_Table <- rbind(Match_Tab1, Match_Tab2)
colnames(LocName_Match_Table) <- c("Data_Names", "Ref_Names")
LocName_Match_Table <- unique(LocName_Match_Table)

rownames(LocName_Match_Table) <- NULL

if(nrow(LocName_Match_Table) >0) {
	# Replace unmatched location names in the data
	for (nR in 1:nrow(LocName_Match_Table)) {
	  Phenotypes_AgSd_Tr_Filt_DF[,"Location"] <- gsub(LocName_Match_Table[nR, "Data_Names"], 
													  LocName_Match_Table[nR, "Ref_Names"], 
													  Phenotypes_AgSd_Tr_Filt_DF[,"Location"])
	}
}


###tolower
capwords <- function(s, strict = FALSE) {
  cap <- function(s) paste(toupper(substring(s, 1, 1)),
                           {s <- substring(s, 2); if(strict) tolower(s) else s},
                           sep = "", collapse = " " )
  sapply(strsplit(s, split = " "), cap, USE.NAMES = !is.null(names(s)))
}


#### 

# Load necessary library
library(gtools)

# Define reference and output trait names
TraitNames_Ref <- c("Height", "Lodging", "Maturity", "SeedSize", "SeedQuality", 
                    "Protein", "Oil", "YieldBuA", "YieldRank", "SeedLinoleicAcid", 
                    "SeedLinolenicAcid", "SeedOleicAcid", "SeedPalmiticAcid", 
                    "SeedRaffinose", "SeedStachyose", "SeedStearicAcid", 
                    "SeedSucrose", "SeedSugarTotal")

SdTraitNames_Data <- c("PALMITIC", "STEARIC", "OLEIC", "LINOLEIC", "LINOLENIC")
SdTraitNamesSUG_Data <- c("SUCROSE", "RAFFINOSE", "STACHYOSE", "TOTAL")

TraitNamesAg <- c("YIELD \\(bu/a\\)", "YIELD RANK", "MATURITY", "LODGING", 
                  "PLANT HEIGHT", "SEED SIZE", "SEED QUALITY", "PROTEIN", "OIL")

cNames_DF_Out <- c("YIELD (bu/a)", "YIELD RANK", "MATURITY (date)", "LODGING (score)", 
                   "PLANT HEIGHT (inches)", "SEED SIZE (g/100)", "SEED QUALITY (score)", 
                   "PROTEIN (%)", "OIL (%)", "FATTY ACID, PALMITIC (%)", 
                   "FATTY ACID, STEARIC (%)", "FATTY ACID, OLEIC (%)", 
                   "FATTY ACID, LINOLEIC (%)", "FATTY ACID, LINOLENIC (%)", 
                   "SEED SUGAR, SUCROSE (%)", "SEED SUGAR, RAFFINOSE (%)", 
                   "SEED SUGAR, STACHYOSE (%)", "SEED SUGAR, TOTAL (%)")

# Combine key trait names
TraitNamesKey <- c(TraitNamesAg, SdTraitNames_Data, SdTraitNamesSUG_Data)

# Clean and format trait names
clean_trait_names <- function(names) {
  names <- gsub("[\\\\()/]|PLANT", "", names)  # Remove unwanted characters
  names <- gsub(" ", "", capwords(names, strict = TRUE))  # Capitalize and remove spaces
  return(names)
}

TraitNamesKey_Mod1_Ref <- clean_trait_names(TraitNamesKey)
TraitNamesKey_Mod1_Ref <- gsub("Total","SugarTotal",TraitNamesKey_Mod1_Ref)


# Modify reference names for matching
TraitNames_Ref_Mod <- TraitNames_Ref
initInd <- which(TraitNames_Ref_Mod %in% "SeedLinoleicAcid")
initInd
TraitNames_Ref_Mod[initInd:length(TraitNames_Ref)] <- gsub("Seed", "", TraitNames_Ref[initInd:length(TraitNames_Ref)])

# Create Reference Table
KeyRefTab <- do.call(rbind.data.frame, lapply(TraitNamesKey_Mod1_Ref, function(key) {
  match_index <- grep(paste0("^", key), TraitNames_Ref_Mod, ignore.case = TRUE)
  if (length(match_index) > 0) {
    c(TraitNames_Ref_Mod[match_index[1]], key)
  } else {
    c(NA, key)  # Handle missing matches
  }
}))

colnames(KeyRefTab) <- c("Ref", "Key")

KeyRefTab$Key <- gsub("SugarTotal","Total",KeyRefTab$Key)

# Create Output Table
KeyOutTab <- do.call(rbind.data.frame, lapply(TraitNamesKey, function(key) {
  match_index <- grep(key, cNames_DF_Out, ignore.case = TRUE)
  if (length(match_index) > 0) {
    c(key, cNames_DF_Out[match_index[1]])
  } else {
    c(key, NA)  # Handle missing matches
  }
}))
colnames(KeyOutTab) <- c("Key", "Out")

# Clean keys in the Output Table for consistency
KeyOutTab[,"Key"] <- clean_trait_names(KeyOutTab[,"Key"])

# Merge Reference and Output Tables
MapTable <- merge(KeyRefTab, KeyOutTab, by = "Key", all = TRUE)

# Match output column names to reference names
match_indices <- match(cNames_DF_Out, MapTable[,"Out"])
mapped_refs <- MapTable[match_indices, "Ref"]

# Ensure all columns in the data frame are matched
cNames_DF <- colnames(Phenotypes_AgSd_Tr_Filt_DF)
trt_mtch_indices <- match(cNames_DF, MapTable[,"Out"])
cNames_DF[!is.na(trt_mtch_indices)] <- MapTable[trt_mtch_indices[!is.na(trt_mtch_indices)], "Ref"]

# Update column names in the data frame
colnames(Phenotypes_AgSd_Tr_Filt_DF) <- cNames_DF

# Output a summary of unmatched columns (if any)
unmatched_cols <- cNames_DF_Out[is.na(mapped_refs)]
if (length(unmatched_cols) > 0) {
  warning("The following columns could not be matched: ", paste(unmatched_cols, collapse = ", "))
}

#### 

#### 
##Filter Columns

rmColsFin <- grep("UniqueID",colnames(Phenotypes_AgSd_Tr_Filt_DF))
if(length(rmColsFin)>0) {Phenotypes_AgSd_Tr_Filt_DF_Out <- Phenotypes_AgSd_Tr_Filt_DF[,-rmColsFin]}else{Phenotypes_AgSd_Tr_Filt_DF_Out <- Phenotypes_AgSd_Tr_Filt_DF} 

###
Phenotypes_AgSd_Tr_Filt_DF_Out$Strain <- clean_strain_annotations(Phenotypes_AgSd_Tr_Filt_DF_Out$OriginalStrain)
###

anyNA(Phenotypes_AgSd_Tr_Filt_DF_Out$Strain)
#[1] FALSE
anyNA(Phenotypes_AgSd_Tr_Filt_DF_Out$OriginalStrain)
#[1] FALSE

anyNA(colnames(Phenotypes_AgSd_Tr_Filt_DF_Out))
naColInd <- which(is.na(colnames(Phenotypes_AgSd_Tr_Filt_DF_Out)))
if(length(naColInd)>0){Phenotypes_AgSd_Tr_DF_Out <- Phenotypes_AgSd_Tr_Filt_DF_Out[,-naColInd]}else{Phenotypes_AgSd_Tr_DF_Out <- Phenotypes_AgSd_Tr_Filt_DF_Out}
Phenotypes_AgSd_Trts_Filt_DF_Out <- Phenotypes_AgSd_Tr_DF_Out[,c(1:5,ncol(Phenotypes_AgSd_Tr_DF_Out),c(6:(ncol(Phenotypes_AgSd_Tr_DF_Out )-1)))]

selCols1 <- c("Strain","Year","Test","Location","City","State","OriginalStrain")
selCols2 <- setdiff(colnames(Phenotypes_AgSd_Tr_DF_Out),selCols1)

Phenotypes_AgSd_Trts_Filt_DF_Out <- Phenotypes_AgSd_Tr_DF_Out[,c(selCols1,selCols2)]
dim(Phenotypes_AgSd_Trts_Filt_DF_Out)
#[1] 4854   25

length(unique(Phenotypes_AgSd_Trts_Filt_DF_Out$Strain))
#[1] 414

### Check if ID cols got NA
# apply(Phenotypes_AgSd_Trts_Filt_DF_Out,2,function(x) anyNA(x))
        # Strain           Year           Test       Location           City          State OriginalStrain       YieldBuA      YieldRank 
         # FALSE          FALSE          FALSE          FALSE          FALSE          FALSE          FALSE           TRUE           TRUE 
      # Maturity        Lodging         Height       SeedSize    SeedQuality        Protein            Oil   PalmiticAcid    StearicAcid 
          # TRUE           TRUE           TRUE           TRUE           TRUE           TRUE           TRUE           TRUE           TRUE 
     # OleicAcid   LinoleicAcid  LinolenicAcid        Sucrose      Raffinose      Stachyose     SugarTotal 
          # TRUE           TRUE           TRUE           TRUE           TRUE           TRUE           TRUE 


# OutFiles 

write.csv(Phenotypes_AgSd_Trts_Filt_DF_Out,"phenotypesTable0.csv",quote=FALSE,row.names=FALSE)


###

###### Extract meta table and locations table from test files 

#### Set working directory
setwd("C:/Users/ivanv/Desktop/UMN_Projects/NUST_Projects/NUST_Data/2025/2025_NUST_Processing/")
library(reshape2)

# Define year and test sets
Year <- "2025"
Tests1 <- c("UT00","UT0","UTI","UTII","UTIII","UTIV","PTI","PTIIA","PTIIB","PTIIIA","PTIIIB","PTIV")
Tests2 <- paste(c("UT0","UTI","UTII","UTIII","UTIV"),"TM",sep="")
Tests3 <- paste(c("Seed Traits UT0", "Seed Traits UTI", "Seed Traits UTII", "Seed Traits UTIII", "Seed Traits UTIV"), "TM", sep = "")

# Read lookup table
 Cal_Julian_Lookup_2025 <- read.csv("Cal_Date_JulDay_LookUp_2025.csv", header = TRUE)

# Initialize output list
 PhenotypesTable_Out_List <- list()
 SDTraitValues <- c(FALSE, TRUE)  # Logical values instead of character

######################################################
# Loop over trait types (Agronomic vs. Seed Composition)
  nSD <- 1
  
 # Initialize lists
  PhenotypesTable_List <- list()
  MetaTable_List <- list()
  LocationsTable_List <- list()
  
  # Define trait-specific variables
  SDTraits <- SDTraitValues[nSD]
  
  
  if(SDTraits){
    SdTraits <- c("FATTY ACID, PALMITIC (%)", "FATTY ACID, STEARIC (%)", "FATTY ACID, OLEIC (%)", 
                  "FATTY ACID, LINOLEIC (%)", "FATTY ACID, LINOLENIC (%)")
    SdTraitNames <- c("PALMITIC", "STEARIC", "OLEIC", "LINOLEIC", "LINOLENIC")
    
    SdTraitsSUG <- c("SEED SUGAR, SUCROSE (%)", "SEED SUGAR, RAFFINOSE (%)", 
                     "SEED SUGAR, STACHYOSE (%)", "SEED SUGAR, TOTAL (%)")
    SdTraitNamesSUG <- c("SUCROSE", "RAFFINOSE", "STACHYOSE", "TOTAL")
    
    Tests <- Tests3
    Traits <- c(SdTraits,SdTraitsSUG)
    TraitNames <- c(SdTraitNames, SdTraitNamesSUG)
  }else{ 
    Traits <- c("YIELD (bu/a)", "YIELD RANK", "MATURITY (date)", "LODGING (score)", 
                "PLANT HEIGHT (inches)", "SEED SIZE (g/100)", "SEED QUALITY (score)", 
                "PROTEIN (%)", "OIL (%)")
    TraitNames <- c("YIELD", "MATURITY", "LODGING", "PLANT HEIGHT", "SEED SIZE", 
                    "SEED QUALITY", "PROTEIN", "OIL")
    Tests <- c(Tests1, Tests2)
	
	TraitsMeta <- c("YIELD (bu/a)", "MATURITY (date)")
	TraitNamesMeta <- c("YIELD", "MATURITY")
  }
  
  # Process each test file
  for(Test in Tests){
    fileName <- paste0(Test, ".csv")
    
    if (!file.exists(fileName)) {
      warning(paste("File not found:", fileName))
      next
    }
    
    # Read and clean data
    Trial_File <- read.csv(fileName, header = TRUE, stringsAsFactors = FALSE)
    Trial_File <- as.data.frame(lapply(Trial_File, as.character))
    
    # Remove empty rows and columns
    Trial_File_Filt <- Trial_File[rowSums(is.na(Trial_File) | Trial_File == "") != ncol(Trial_File), ]
    Trial_File_Filt <- Trial_File_Filt[, colSums(is.na(Trial_File_Filt) | Trial_File_Filt == "") != nrow(Trial_File_Filt)]
    
    # Clean strain names
    Trial_File_Filt$X <- sapply(Trial_File_Filt$X, clean_strain_encoding)
    	
	# Extract relevant data
    # beginCol <- which(colSums(sapply(TraitNames, function(y) grepl(y, Trial_File_Filt, fixed = TRUE))) >= length(TraitNames))
    beginCol <- which(sum(sapply(TraitNames, function(y) grepl(y, Trial_File_Filt, fixed = TRUE))) >= length(TraitNames))
	
	if(length(beginCol) == 0) {
      warning(paste("No trait column found in:", fileName))
      next
    }
    
    # Process trait tables
    TraitsTable_List <- list()
    TrtTab_Filt_Lng_List <- list()

	for(nTrt in seq_along(TraitsMeta)){
		
	# Locate trait rows
	 trt <- TraitsMeta[nTrt]
	 trtIndx <- unlist(sapply(TraitNamesMeta, function(y) grep(y,Trial_File_Filt[, beginCol], fixed = FALSE)))
		  
	 if(length(trtIndx) == 0) next

	 if(nTrt < length(TraitsMeta)){
	   Filt0 <- Trial_File_Filt[trtIndx[nTrt]:(trtIndx[nTrt + 1] - 1), beginCol:ncol(Trial_File_Filt)]
	 }else{
	  finRow <- grep("LODGING",Trial_File_Filt[,beginCol])
	  Filt0 <- Trial_File_Filt[trtIndx[nTrt+1]:(finRow-1), beginCol:ncol(Trial_File_Filt)]
	 }
	 
	 Filt0 <- Filt0[,colSums(is.na(Filt0) | Filt0 == "") != nrow(Filt0)]
	 print(dim(Filt0))
	 TraitsTable_List[[nTrt]] <- Filt0
		
	 if(nTrt==1){
      Strt_Strain_Name <- TraitsTable_List[[1]][which(TraitsTable_List[[1]][,initCol] %in% "Strain")+1,initCol]
      End_Strain_Name <- TraitsTable_List[[1]][which(TraitsTable_List[[1]][,initCol] %in% "Location Mean")-1,initCol]
      StrainNames_Init <- which(TraitsTable_List[[nTrt]][,initCol] %in% Strt_Strain_Name)
      StrainNames_Final <- which(TraitsTable_List[[nTrt]][,initCol] %in% End_Strain_Name)
      StrainNames <- TraitsTable_List[[nTrt]][c(StrainNames_Init:StrainNames_Final),initCol]
      print(paste(Test,StrainNames_Init,StrainNames_Final,sep="_"))
     }
      
    
     StrRowInd <- which(TraitsTable_List[[nTrt]][,initCol] %in% "Strain")
	 upRowInd <- which(TraitsTable_List[[nTrt]][,initCol+1] %in% "Mean") 
	 EndRow <- nrow(TraitsTable_List[[nTrt]])
 
     # if(nTrt==1){ 
     # upRowInd <- which(TraitsTable_List[[nTrt]][,initCol+1] %in% "Yield")-1 
     # }else{
     # }
   
     StrainInd <- which(TraitsTable_List[[nTrt]][c(upRowInd:EndRow),initCol] %in% StrainNames)
     lowRowInd <- StrainInd[length(StrainInd)]
  
## Extract Table and set colnames
     finCol <- ncol(TraitsTable_List[[nTrt]])
     StrRowTabInd <- which(TraitsTable_List[[nTrt]][,initCol] %in% "Strain")
     TrtTab <- as.data.frame(TraitsTable_List[[nTrt]][c(upRowInd:EndRow)[StrainInd],c(initCol:finCol)])
     
	 cNameInit <- 2
	 cNameFin <- 4 
     cNames <- TraitsTable_List[[nTrt]][c(cNameInit:cNameFin),]	 
	 colnames(TrtTab) <- unlist(lapply(c(1:ncol(cNames)),function(x) paste(paste(gsub("-","",cNames[1:2,x]),collapse=""),cNames[3,x],sep="_")))
	 colnames(TrtTab) <- gsub(" ","",colnames(TrtTab))
    
     TraitsTable <- TraitsTable_List[[nTrt]]
	
		  
	##### Meta Table and Loc Table
    
	if(TraitsMeta[nTrt] == "YIELD (bu/a)"){ 
			  strtVar <- "Location Mean"
			  endVar <- "Reps"
			  
			  initCol <- beginCol
			  init <- which(TraitsTable_List[[nTrt]][,initCol] %in% strtVar)
			  fin <- which(TraitsTable_List[[nTrt]][,initCol] %in% endVar)
			  finCol <- ncol(TraitsTable_List[[nTrt]])
			  MetaTab <- as.data.frame(TraitsTable_List[[nTrt]][c(init:fin),initCol:finCol])
			  colnames(MetaTab) <- colnames(TrtTab)
			  colnames(MetaTab)[1] <- "Meta_data_type"
			  MetaTab$Meta_data_type <- as.factor(MetaTab$Meta_data_type)
			  MetaTable0 <- melt(MetaTab,id.vars="Meta_data_type")
			  MetaTableVar1 <- rep(paste(Year,Test,sep="_"),nrow(MetaTable0))
			  MetaTableVar2 <- rep(paste(Test,Year,sep="_"),nrow(MetaTable0))
			  MetaTable<- cbind.data.frame(MetaTableVar1,MetaTableVar2,MetaTable0[,"variable"],MetaTable0[,"Meta_data_type"],MetaTable0[,"value"])
			  colnames(MetaTable) <- c("Year-Test","Test-Year","Location","Meta_data_type","Value")
	}
    if(TraitsMeta[nTrt] == "MATURITY (date)"){
	          initCol <- beginCol
			  rowVars <- c("Date Planted","Days to Mature")
			  rowVarIndx <- which(TraitsTable_List[[nTrt]][,initCol] %in% rowVars)
			  finCol <- ncol(TraitsTable_List[[nTrt]])
			  LocTab0 <-  as.data.frame(TraitsTable_List[[nTrt]])[rowVarIndx,c(initCol:finCol)]
			  colnames(LocTab0) <- colnames(TrtTab)
			  colnames(LocTab0)[1] <- "Location_Meta_Vars"
			  if(length(apply(LocTab0,1,function(x) which(x=="")))>0){LocTab <-t(apply(LocTab0,1,function(x) {if(length(which(x==""))>0){ x[which(x=="")] <- NA;x}else{x}}))
			  }else{
				LocTab <- LocTab0
			  }
			  LocTab <- as.data.frame(LocTab)
			 
			  LocationsTable0 <- melt(LocTab,id.vars="Location_Meta_Vars")
			  LocTableVar1 <- rep(paste(Year,Test,sep="_"),nrow(LocationsTable0))
			  LocationsTable <- cbind.data.frame(LocTableVar1, LocationsTable0[,"variable"],LocationsTable0[,"Location_Meta_Vars"],LocationsTable0[,"value"])
			  colnames(LocationsTable) <- c("Year-Test","Location","Meta_data_type","Value")
	}
	
	}
 
	MetaTable_List[[Test]] <- MetaTable
	LocationsTable_List[[Test]] <- LocationsTable 
}

MetaTable0 <- do.call(rbind.data.frame,lapply(MetaTable_List,function(x) x)) 
MetaTable00 <- droplevels(MetaTable0[grep("Mean",MetaTable0$Location,invert=TRUE),])
MetaTable <- droplevels(MetaTable00[MetaTable00$Location!="_",])

LocationsTable0 <- do.call(rbind.data.frame,lapply(LocationsTable_List,function(x) x)) 
LocationsTable <- droplevels(LocationsTable0[grep("Mean",LocationsTable0$Location,invert=TRUE),])


write.csv(MetaTable,"MetaTable.csv",row.names=FALSE,quote=FALSE)
write.csv(LocationsTable,"LocationsTable.csv",row.names=FALSE,quote=FALSE)

###


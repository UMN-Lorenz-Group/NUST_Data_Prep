### 2025
source("C:/Users/ivanv/Desktop/UMN_GIT/NUST_Data_Prep/nust_utils.R")
setwd("C:/Users/ivanv/Desktop/UMN_Projects/NUST_Projects/NUST_Data/2025/2025_NUST_Processing/")
library(reshape2)

Year <- "2025"
Tests1 <- c("UT00","UT0","UTI","UTII","UTIII","UTIV","PTI","PTIIA","PTIIB","PTIIIA","PTIIIB","PTIV")
Tests2 <- paste(c("UT0","UTI","UTII","UTIII","UTIV"),"TM",sep="") 

###### Locations Table from NUST 2025 Processing from test data files 
###### Contains the following fields 	Year-Test	Location	Meta_data_type	Value
###### For locations table in Soybase portal format, cast locations data for meta data type in wide format
###### add contributor, lat, long


LocationsTable <- read.csv("LocationsTable.csv") 

rmMeanInd <- grep("Mean",LocationsTable$Location)
if(length(rmMeanInd)>0){ 
  LocationsTableMod <- LocationsTable[-rmMeanInd,]}else{
  LocationsTableMod <- LocationsTable
} 

data.Cast <- dcast(Year.Test+Location ~ Meta_data_type,data=LocationsTableMod)  
YrTstTable <- do.call(rbind,lapply(strsplit(data.Cast$`Year.Test`,"_"),function(x) x))
data.Cast$Year <- YrTstTable [,1]
data.Cast$Test <- YrTstTable [,2]

###
data.Cast$LocationMod <- data.Cast$Location

###### Note:  In data.Cast, Location is location_state
data.Cast$Location <- unlist(lapply(data.Cast$LocationMod,function(x) strsplit(x,"_")[[1]][1]))
data.Cast$State <-  unlist(lapply(data.Cast$LocationMod,function(x) strsplit(x,"_")[[1]][2]))


df <- data.Cast

# Unify location names
df$Location <- standardize_location_names(df$Location)

# Standardize state names



data.Cast <- df
str(data.Cast)

###

data.Cast$LocationMod <- paste(data.Cast$Location,data.Cast$State,sep="_")
data.Cast$LocationMod <- gsub("\\*","",data.Cast$LocationMod)
data.Cast$LocationMod <- gsub("no data","",data.Cast$LocationMod)

unique(data.Cast$LocationMod)
 
###

### 

NUST_Loc_Info <- read.csv("2025_NUST_Locations_PlotInfo.csv",header=T)
colnames(NUST_Loc_Info) <- gsub("X\\.\\.","",colnames(NUST_Loc_Info))

NAIndicesLoc <- which(is.na(NUST_Loc_Info[,"Entries"]))
if(length(NAIndicesLoc)>=1){NUST_Loc_Info_Filt <- NUST_Loc_Info[-NAIndicesLoc,]}else{NUST_Loc_Info_Filt <- NUST_Loc_Info}

NUST_Loc_Info_Filt$location <- gsub("-","",NUST_Loc_Info_Filt$location)
NUST_Loc_Info_Filt$location <- gsub("Ottawa[A-Z]*","Ottawa",NUST_Loc_Info_Filt$location)

NUST_Loc_Info_Filt$State.Prov <- gsub("MAN","MN",NUST_Loc_Info_Filt$State.Prov)

NUST_Loc_Info_Filt$location <- standardize_location_names(NUST_Loc_Info_Filt$location)

#### 
NUST_Loc_Info_Filt$LocationMod <- paste(NUST_Loc_Info_Filt$location,NUST_Loc_Info_Filt$State.Prov,sep="_") 
NUST_Loc_Info_Filt$LocationMod <- gsub("\\*","",NUST_Loc_Info_Filt$LocationMod)
NUST_Loc_Info_Filt$LocationMod <- gsub("ManhattanLocA_KS","Manhattan_KS",NUST_Loc_Info_Filt$LocationMod)
NUST_Loc_Info_Filt$LocationMod <- gsub("LocB_KS","ManhattanB_KS",NUST_Loc_Info_Filt$LocationMod)

levels(factor(NUST_Loc_Info_Filt$LocationMod))

locStateLevs <- levels(factor(data.Cast$LocationMod))

### Check if thi diff is null
setdiff(locStateLevs,levels(factor(NUST_Loc_Info_Filt$LocationMod)))
setdiff(levels(factor(NUST_Loc_Info_Filt$LocationMod)),locStateLevs)

###

data.Cast$uniqID <- paste(data.Cast$Year.Test,data.Cast$LocationMod,sep="_")

NUST_Loc_Info_Filt$trial <-gsub("24","2025_",NUST_Loc_Info_Filt$trial)
NUST_Loc_Info_Filt$uniqID <- paste(NUST_Loc_Info_Filt$trial,NUST_Loc_Info_Filt$LocationMod,sep="_")

Locations_Meta_Data <- merge(data.Cast,NUST_Loc_Info_Filt,by="uniqID") 
colnames(Locations_Meta_Data) <- gsub(".x","",colnames(Locations_Meta_Data))

Locations_Meta_Data_Filt <- Locations_Meta_Data[,c(colnames(data.Cast),"Grower","Lat","Long","Planting.Date","Row.Width..in.")]


# In the previous versions, row sp had to be extracted from meta table, from 2023/2025 - this information is available in 
### NUST_Master file 

# Create Planting and Maturity Dates
LocationsTable_2025 <- Locations_Meta_Data_Filt
LocationsTable_2025$PlantingDate <- as.Date(
  paste(LocationsTable_2025$`Planting.Date`, "-", LocationsTable_2025$Year, sep = ""), 
  format = "%d-%b-%Y"
)
LocationsTable_2025$MaturityDate <- LocationsTable_2025$PlantingDate + 
  as.integer(as.numeric(LocationsTable_2025$`Days to Mature`))

# Select and rename relevant columns
LocationsTable_2025_Mod <- LocationsTable_2025[, c("Year", "Test", "Location", "State","Lat", "Long", "Grower", "PlantingDate", "MaturityDate")]
colnames(LocationsTable_2025_Mod) <- c("Year", "Test", "Location", "State", "lat", "lon","Conductor","PlantingDate", "MaturityDate")


 LocationsTable_2025_Mod$Location <- gsub("Steven's","Stevens",LocationsTable_2025_Mod$Location)
############################################
#### Check location names against NUST location names 

# Load NUST location reference
NUST_Locations_Ref <- read.csv("NUST_Location_Names.csv", header = TRUE)

# Extract unique NUST location names
NUST_Locations <- unlist(as.vector(NUST_Locations_Ref[, c("Location1", "Location2")]))
NUST_Location_Names <- NUST_Locations[NUST_Locations != ""]
NUST_Locations_Lev <- unique(NUST_Location_Names)

# Extract unique data location names
Data_Location_Names <- paste(LocationsTable_2025_Mod[,"Location"], LocationsTable_2025_Mod[,"State"], sep = "_")
Data_Locations_Lev <- unique(gsub(" ", "", Data_Location_Names))

# Identify unmatched locations
remNames1 <- setdiff(Data_Locations_Lev, NUST_Locations_Lev)
remLocNames1 <- sapply(strsplit(remNames1, "_"), function(x) x[1])

remNames2 <- setdiff(NUST_Locations_Lev, Data_Locations_Lev)
remLocNames2 <- sapply(strsplit(remNames2, "_"), function(x) x[1])

# Create match tables for unresolved location names
Match_Tab1 <- do.call(rbind, lapply(remLocNames1, function(x) {
  match_indices <- grep(x, remLocNames2)
  if (length(match_indices) > 0) {
    c(x, remLocNames2[match_indices[1]])
  } else {
    NULL
  }
}))
if (!is.null(Match_Tab1)) {
  colnames(Match_Tab1) <- c("Data_Names", "Ref_Names")
}

Match_Tab2 <- do.call(rbind, lapply(remLocNames2, function(x) {
  match_indices <- grep(x, remLocNames1)
  if (length(match_indices) > 0) {
    c(remLocNames1[match_indices[1]], x)
  } else {
    NULL
  }
}))
if (!is.null(Match_Tab2)) {
  colnames(Match_Tab2) <- c("Data_Names", "Ref_Names")
}

# Combine match tables and remove duplicates
LocName_Match_Table <- unique(rbind(Match_Tab1, Match_Tab2))

LocationsTable_2025_Mod2 <- LocationsTable_2025_Mod
# Replace unmatched location names in the data
if (!is.null(LocName_Match_Table)) {
  for (nR in 1:nrow(LocName_Match_Table)) {
    LocationsTable_2025_Mod2[,"Location"] <- gsub(
      LocName_Match_Table[nR, "Data_Names"], 
      LocName_Match_Table[nR, "Ref_Names"], 
      LocationsTable_2025_Mod2[,"Location"]
    )
  }
}

LocationsTable_2025_Mod[1:5,]
# Save the updated table
write.csv(LocationsTable_2025_Mod2, "LocationsTable1.csv", row.names = FALSE, quote = FALSE)








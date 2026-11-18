#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Engine/HitResult.h"
#include "TimerManager.h"
#include "WatooMPickup.generated.h"

class USphereComponent;
class UStaticMeshComponent;
class URotatingMovementComponent;
class UWatooMItemData;
class AWatooMCombatCharacter;

/**
 * A world pickup for one UWatooMItemData: weapon, spell, ammo or consumable. Server-authoritative: only the server reacts to
 * the overlap, applies the item and hides the pickup; the hidden state replicates. Place it with level.place_actor and set
 * Item (unreal_combat.py "place" entries with "item"). RespawnSeconds 0 = once.
 */
UCLASS()
class WATOOMCOMBAT_API AWatooMPickup : public AActor
{
	GENERATED_BODY()
public:
	AWatooMPickup();

	UPROPERTY(EditAnywhere, BlueprintReadOnly, ReplicatedUsing = OnRep_Item, Category = "Pickup") TObjectPtr<UWatooMItemData> Item;
	/** Seconds until the pickup comes back after being taken; 0 = never. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Pickup") float RespawnSeconds = 0.f;

	/** Server: give the item to a character. False when it cannot use it (dead, full health for a pure heal, ...). */
	UFUNCTION(BlueprintCallable, BlueprintAuthorityOnly, Category = "Pickup") bool GiveTo(AWatooMCombatCharacter* Character);
	UFUNCTION(BlueprintPure, Category = "Pickup") bool IsAvailable() const { return bAvailable; }

	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
	virtual void OnConstruction(const FTransform& Transform) override;

protected:
	virtual void BeginPlay() override;

	UPROPERTY(VisibleAnywhere, Category = "Pickup") TObjectPtr<USphereComponent> Trigger;
	UPROPERTY(VisibleAnywhere, Category = "Pickup") TObjectPtr<UStaticMeshComponent> Mesh;
	UPROPERTY(VisibleAnywhere, Category = "Pickup") TObjectPtr<URotatingMovementComponent> Spin;
	UPROPERTY(ReplicatedUsing = OnRep_Available) bool bAvailable = true;

	UFUNCTION() void OnOverlap(UPrimitiveComponent* OverlappedComp, AActor* Other, UPrimitiveComponent* OtherComp, int32 BodyIndex, bool bFromSweep, const FHitResult& Sweep);
	UFUNCTION() void OnRep_Item();
	UFUNCTION() void OnRep_Available();
	void SetAvailable(bool bNow);
	void ApplyLook();

	FTimerHandle RespawnTimer;
};
